from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from system_components.data_management_layer.data_preprocessing import FEATURES, case_features, prepare_frame
from system_components.neuro_symbolic_reasoning_layer.candidate_action_generation import ACTIONS, rank_actions, softmax
from system_components.neuro_symbolic_reasoning_layer.intent_aware_decision import ALLOWED_ACTIONS, apply_intent
from system_components.neuro_symbolic_reasoning_layer.weighted_soft_rule_reasoning import DEFAULT_RULES, apply_rules, evaluate_rule, hard_rejected_actions
from system_components.predictive_analytics_layer.predictive_attribution import (
    PredictiveAttribution,
    SupervisedActionEvidence,
)
from system_components.trust_and_decision_layer.explanation_generation import explain
from system_components.trust_and_decision_layer.trust_calibration import fit_temperature


# Frozen from the validation-only risk-coverage analysis.
MIN_AUTO_CONFIDENCE = .35
MIN_TOP_TWO_MARGIN = .02


@dataclass(frozen=True)
class ScoringParameters:
    rule_penalty: float
    intent_strength: float
    channel_strength: float
    investigate_boost: float = .10


@dataclass
class EngineResult:
    action: str
    confidence: float
    raw_confidence: float
    performance_score: float
    confidence_level: str
    ranked_actions: list[dict[str, Any]]
    attribution: list[dict[str, Any]]
    channel_attribution: list[dict[str, Any]]
    rule_results: list[dict[str, Any]]
    explanation: dict[str, str]
    latency_ms: float
    calibration_status: str
    action_evidence_status: str
    decision_status: str
    decision_reasons: list[str]
    feasible_actions: list[str]
    hard_rejected_actions: list[str]
    coverage_status: str = "IN_SCOPE"
    coverage_reasons: list[str] = field(default_factory=list)


def selective_decision_status(
    action: str,
    confidence: float,
    ranked_actions: list[dict[str, Any]],
    rule_results: list[dict[str, Any]],
    budget: float | None,
    *,
    no_safe_action: bool = False,
    coverage_reasons: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Apply the frozen review policy without changing the recommended action."""

    if no_safe_action:
        return "NO SAFE RECOMMENDATION", [
            "No executable campaign action passed the hard safeguards; manual review is required."
        ]
    if coverage_reasons:
        return "HUMAN REVIEW REQUIRED", coverage_reasons
    if action == "Investigate":
        return "HUMAN REVIEW REQUIRED", ["The selected action is Investigate."]
    if action == "Increase" and budget is None:
        return "HUMAN REVIEW REQUIRED", ["Budget is missing, so expansion feasibility cannot be evaluated."]
    reasons = []
    margin = confidence - (float(ranked_actions[1]["score"]) if len(ranked_actions) > 1 else 0.0)
    if confidence < MIN_AUTO_CONFIDENCE:
        reasons.append(f"Calibrated confidence is below {MIN_AUTO_CONFIDENCE:.2f}.")
    if margin < MIN_TOP_TWO_MARGIN:
        reasons.append(f"The top-two action margin is below {MIN_TOP_TWO_MARGIN:.2f}.")
    if any(item["action"] == action and item["triggered"] for item in rule_results):
        reasons.append("The selected action retains a triggered soft safeguard.")
    return ("CHECK ADVISED", reasons) if reasons else ("RECOMMEND", [])


class RecommendationEngine:
    def __init__(
        self,
        dataset: Path,
        annotation_dataset: Path | None = None,
        audited_benchmark: Path | None = None,
        seed: int = 42,
    ) -> None:
        torch.manual_seed(seed)
        np.random.seed(seed)
        self.seed = seed
        self.data = prepare_frame(dataset)
        train_end = max(1, int(len(self.data) * .70))
        validation_end = max(train_end + 1, int(len(self.data) * .85))
        self.train = self.data.iloc[:train_end].copy()
        self.validation = self.data.iloc[train_end:validation_end].copy()
        self.test = self.data.iloc[validation_end:].copy()
        self._set_coverage_reference(self.train)
        self.predictive = PredictiveAttribution(self.train)
        self.action_supervision: SupervisedActionEvidence | None = None
        self.annotation_status = "none"
        if annotation_dataset is not None and annotation_dataset.exists():
            annotated = prepare_frame(annotation_dataset)
            required = {
                "Campaign_ID",
                "Reviewer_Intent",
                "Reviewer_Action",
                "Annotation_Status",
            }
            if not required.issubset(annotated.columns):
                raise ValueError("Annotation dataset is missing supervised-action fields.")
            if not annotated["Annotation_Status"].eq("DevelopmentOnly").all():
                raise ValueError("Unaudited action supervision must remain DevelopmentOnly.")
            if len(annotated) != len(self.data):
                raise ValueError("Annotation and authentic datasets must have equal coverage.")
            if not annotated["Campaign_ID"].equals(self.data["Campaign_ID"]):
                raise ValueError("Annotation and authentic datasets must align by Campaign_ID.")
            self.action_supervision = SupervisedActionEvidence(
                annotated.iloc[:train_end].copy()
            )
            self.annotation_status = "user_provided_development"
        # Compatibility attributes for experiment notebooks and tests.
        self.scaler, self.model, self.channel_evidence = self.predictive.scaler, self.predictive.model, self.predictive.channel_evidence
        self.default_rules = [
            {"id": index, "code": rule[0], "name": rule[1], "weight": rule[4], "priority": rule[5], "active": True}
            for index, rule in enumerate(DEFAULT_RULES, 1)
        ]
        self.scoring = ScoringParameters(
            rule_penalty=.20,
            intent_strength=.20,
            channel_strength=.10,
        )
        self.temperature = 1.0
        self.calibration_status = "pending_human_annotations"
        self._fit_audited_temperature(
            audited_benchmark or dataset.with_name("benchmark_audited.csv")
        )

    def _model_evidence(self, features: dict[str, float], explain_result: bool = False):
        return self.predictive.evidence(features, explain_result)

    def _channels(self, case: dict[str, Any]):
        return self.predictive.channels(case)

    _rule_score = staticmethod(evaluate_rule)

    def _fit_audited_temperature(self, benchmark: Path) -> None:
        if not benchmark.exists():
            return
        audited = pd.read_csv(benchmark)
        required = {"Campaign_ID", "Adjudicated_Intent", "Adjudicated_Action", "Annotation_Status"}
        if len(audited) < 120 or not required.issubset(audited.columns):
            return
        if not audited.Annotation_Status.eq("Audited").all():
            return
        prepared = prepare_frame(benchmark)
        train_end = max(1, int(len(prepared) * .70))
        validation_end = max(train_end + 1, int(len(prepared) * .85))
        supervised_train = prepared.iloc[:train_end].rename(
            columns={
                "Adjudicated_Intent": "Reviewer_Intent",
                "Adjudicated_Action": "Reviewer_Action",
            }
        )
        self._set_coverage_reference(supervised_train)
        self.action_supervision = SupervisedActionEvidence(supervised_train)
        self.annotation_status = "audited_human_benchmark"
        validation = prepared.iloc[train_end:validation_end]
        logits, labels = [], []
        for row in validation.to_dict("records"):
            action = str(row["Adjudicated_Action"])
            intent = str(row["Adjudicated_Intent"])
            if action not in ACTIONS or intent not in ALLOWED_ACTIONS:
                return
            raw, *_ = self._score(row, self.default_rules, intent, "full", self.scoring)
            logits.append(raw)
            labels.append(ACTIONS.index(action))
        if len(logits) != len(validation) or not logits:
            return
        self.temperature = fit_temperature(logits, labels)
        self.calibration_status = "calibrated"

    def _set_coverage_reference(self, frame: pd.DataFrame) -> None:
        self.coverage_bounds = {
            feature: (float(frame[feature].min()), float(frame[feature].max()))
            for feature in FEATURES
        }
        self.coverage_channels = {
            channel.strip().casefold()
            for value in frame["Channel_Used"].astype(str)
            for channel in value.split(",")
            if channel.strip()
        }

    def coverage_check(self, case: dict[str, Any]) -> tuple[str, list[str]]:
        """Check whether a case lies inside the training-only benchmark envelope."""

        features = case_features(case)
        outside = [
            feature for feature, value in features.items()
            if not self.coverage_bounds[feature][0] <= value <= self.coverage_bounds[feature][1]
        ]
        channel_value = case.get("channels", case.get("Channel_Used", ""))
        channel_items = channel_value if isinstance(channel_value, (list, tuple, set)) else str(channel_value).split(",")
        channels = {str(channel).strip().casefold() for channel in channel_items if str(channel).strip()}
        unseen = sorted(channels - self.coverage_channels)
        reasons = []
        if outside:
            reasons.append("Outside the training benchmark range: " + ", ".join(outside) + ".")
        if unseen:
            reasons.append("Unseen campaign channel: " + ", ".join(unseen) + ".")
        return ("OUT_OF_BENCHMARK_COVERAGE", reasons) if reasons else ("IN_SCOPE", [])

    def _score(self, case: dict[str, Any], rules: list[dict[str, Any]], intent: str, variant: str, parameters: ScoringParameters, explain: bool = False):
        features = case_features(case)
        campaign_probabilities, attribution = self.predictive.evidence(features, explain)
        probabilities = campaign_probabilities
        if variant == "actionnet_only" and self.action_supervision is None:
            raise RuntimeError("ActionNet-only evaluation requires audited ActionNet supervision.")
        if self.action_supervision is not None:
            supervised_intent = intent if variant not in {"without_intent", "backbone"} else None
            action_evidence = self.action_supervision.evidence(features, supervised_intent)
            if variant == "actionnet_only":
                probabilities = action_evidence
            elif variant not in {"campaignnet_only"}:
                probabilities = .25 * campaign_probabilities + .75 * action_evidence
        smoothed = .90 * probabilities + .10 / len(ACTIONS)
        scores = {action: float(smoothed[index]) for index, action in enumerate(ACTIONS)}
        channels = self.predictive.channels(case)
        channel_signal = statistics_mean([float(item["contribution"]) for item in channels], .5)
        evidence_only = variant in {"backbone", "campaignnet_only", "actionnet_only", "fused_evidence"}
        if not evidence_only:
            scores["Increase"] += parameters.channel_strength * (channel_signal - .5)
            scores["Reduce"] += parameters.channel_strength * (.5 - channel_signal)
            scores["Maintain"] += parameters.channel_strength * (.25 - abs(channel_signal - .5))

        budget_value = case.get("budget", case.get("Budget"))
        budget = None if budget_value in {None, ""} else float(budget_value)
        rule_results = [] if variant == "without_rules" or evidence_only else apply_rules(
            scores, rules, features, intent, budget, parameters.rule_penalty,
            parameters.investigate_boost, variant == "without_intent",
        )
        if variant != "without_intent" and not evidence_only:
            apply_intent(scores, intent, parameters.intent_strength)
        return np.array([scores[action] for action in ACTIONS]), rule_results, probabilities, attribution, channels

    def recommend(self, case: dict[str, Any], rules: list[dict[str, Any]], intent: str, risk: str = "Balanced", ablation: str = "full") -> EngineResult:
        started = time.perf_counter()
        raw, rule_results, probabilities, attribution, channels = self._score(case, rules, intent, ablation, self.scoring, explain=True)
        if risk == "Conservative":
            raw[ACTIONS.index("Increase")] -= .18
            raw[ACTIONS.index("Investigate")] += .12
        elif risk == "Aggressive":
            raw[ACTIONS.index("Increase")] += .14
            raw[ACTIONS.index("Investigate")] -= .08
        raw_probabilities = softmax(raw)
        temperature = (
            1.0
            if ablation in {
                "without_calibration", "backbone", "campaignnet_only",
                "actionnet_only", "fused_evidence",
            }
            else self.temperature
        )
        result_calibration_status = (
            self.calibration_status
            if ablation not in {
                "without_calibration", "backbone", "campaignnet_only",
                "actionnet_only", "fused_evidence",
            }
            else "uncalibrated_ablation"
        )
        ranked = rank_actions(raw, temperature)
        selected, confidence = str(ranked[0]["action"]), float(ranked[0]["score"])
        performance = float(sum(probabilities[index] * (.90, .55, .25, .45)[index] for index in range(4)))
        activated = [item for item in rule_results if item["action"] == selected and item["triggered"]]
        explanation = explain(
            selected,
            confidence,
            intent,
            attribution,
            channels,
            activated,
            result_calibration_status,
        )
        action_evidence_status = {
            "audited_human_benchmark": "audited_actionnet",
            "user_provided_development": "development_actionnet",
        }.get(self.annotation_status, "campaignnet_only_fallback")
        if action_evidence_status == "campaignnet_only_fallback":
            fallback = (
                "Supervised ActionNet evidence was unavailable; the recommendation "
                "used CampaignNet evidence only."
            )
            existing = explanation.get("caveat", "").strip()
            explanation["caveat"] = f"{existing} {fallback}".strip()
        budget_value = case.get("budget", case.get("Budget"))
        budget = None if budget_value in {None, ""} else float(budget_value)
        coverage_status, coverage_reasons = self.coverage_check(case)
        decision_status, decision_reasons = selective_decision_status(
            selected,
            confidence,
            ranked,
            rule_results,
            budget,
            no_safe_action=set(ACTIONS[:3]).issubset(hard_rejected_actions(rule_results)),
            coverage_reasons=coverage_reasons,
        )
        if ablation == "without_review_gate" and decision_status == "CHECK ADVISED":
            decision_status, decision_reasons = "RECOMMEND", []
        rejected_actions = hard_rejected_actions(rule_results)
        feasible_actions = [action for action in ACTIONS if action not in rejected_actions]
        if decision_status == "NO SAFE RECOMMENDATION":
            caveat = (
                "All executable campaign actions were excluded by hard safeguards; "
                "the displayed Investigate action is a manual-review fallback, not an execution instruction."
            )
            explanation["caveat"] = f"{explanation.get('caveat', '').strip()} {caveat}".strip()
        if ablation == "without_explanation":
            explanation = {}
        return EngineResult(
            selected, confidence, float(raw_probabilities[ACTIONS.index(selected)]), performance,
            "High" if confidence >= .75 else "Medium" if confidence >= .50 else "Low",
            ranked, attribution, channels, rule_results, explanation,
            (time.perf_counter() - started) * 1000,
            result_calibration_status,
            action_evidence_status,
            decision_status,
            decision_reasons,
            feasible_actions,
            rejected_actions,
            coverage_status,
            coverage_reasons,
        )


def statistics_mean(values: list[Any], default: float = 0.0) -> float:
    return float(np.mean(values)) if values else default
