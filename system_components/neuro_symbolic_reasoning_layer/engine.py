from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from baseline_evaluation import conflict_reasons, stratified_split
from system_components.data_management_layer.data_preprocessing import case_features, prepare_frame
from system_components.neuro_symbolic_reasoning_layer.candidate_action_generation import ACTIONS, rank_actions, softmax
from system_components.neuro_symbolic_reasoning_layer.intent_aware_decision import ALLOWED_ACTIONS, apply_intent
from system_components.neuro_symbolic_reasoning_layer.weighted_soft_rule_reasoning import DEFAULT_RULES, apply_rules, evaluate_rule
from system_components.predictive_analytics_layer.predictive_attribution import PredictiveAttribution
from system_components.trust_and_decision_layer.explanation_generation import explain
from system_components.trust_and_decision_layer.trust_calibration import fit_temperature


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


class RecommendationEngine:
    def __init__(self, dataset: Path) -> None:
        torch.manual_seed(42)
        np.random.seed(42)
        self.data = prepare_frame(dataset)
        train_pool_rows, test_rows = stratified_split(self.data.to_dict("records"), .2, 42)
        train_rows, validation_rows = stratified_split(train_pool_rows, .2, 42)
        self.train, self.validation, self.test = (pd.DataFrame(rows) for rows in (train_rows, validation_rows, test_rows))
        self.predictive = PredictiveAttribution(self.train)
        # Compatibility attributes for experiment notebooks and tests.
        self.scaler, self.model, self.channel_evidence = self.predictive.scaler, self.predictive.model, self.predictive.channel_evidence
        self.default_rules = [
            {"id": index, "code": rule[0], "name": rule[1], "weight": rule[4], "priority": rule[5], "active": True}
            for index, rule in enumerate(DEFAULT_RULES, 1)
        ]
        self.scoring = self._tune_scoring()
        self.temperature = self._fit_temperature()

    def _model_evidence(self, features: dict[str, float], explain_result: bool = False):
        return self.predictive.evidence(features, explain_result)

    def _channels(self, case: dict[str, Any]):
        return self.predictive.channels(case)

    _rule_score = staticmethod(evaluate_rule)

    def _score(self, case: dict[str, Any], rules: list[dict[str, Any]], intent: str, variant: str, parameters: ScoringParameters, explain: bool = False):
        features = case_features(case)
        probabilities, attribution = self.predictive.evidence(features, explain)
        smoothed = .90 * probabilities + .10 / len(ACTIONS)
        scores = {action: float(smoothed[index]) for index, action in enumerate(ACTIONS)}
        channels = self.predictive.channels(case)
        channel_signal = statistics_mean([float(item["contribution"]) for item in channels], .5)
        if variant != "backbone":
            scores["Increase"] += parameters.channel_strength * (channel_signal - .5)
            scores["Decrease"] += parameters.channel_strength * (.5 - channel_signal)
            scores["Maintain"] += parameters.channel_strength * (.25 - abs(channel_signal - .5))

        budget_value = case.get("budget", case.get("Budget"))
        budget = None if budget_value in {None, ""} else float(budget_value)
        rule_results = [] if variant in {"without_rules", "backbone"} else apply_rules(
            scores, rules, features, intent, budget, parameters.rule_penalty,
            parameters.investigate_boost, variant == "without_intent",
        )
        if variant not in {"without_intent", "backbone"}:
            apply_intent(scores, intent, parameters.intent_strength)
        return np.array([scores[action] for action in ACTIONS]), rule_results, probabilities, attribution, channels

    def _tune_scoring(self) -> ScoringParameters:
        candidates = [
            ScoringParameters(rule_penalty, intent_strength, channel_strength)
            for rule_penalty in (.10, .20, .30, .40, .50)
            for intent_strength in (.10, .20, .30, .40)
            for channel_strength in (.05, .15, .25)
        ]

        def quality(parameters: ScoringParameters) -> tuple[float, float, float, float]:
            predictions, labels, scenarios, conflicts = [], [], [], []
            for row in self.validation.to_dict("records"):
                raw, *_ = self._score(row, self.default_rules, row["Intent"], "full", parameters)
                action = ACTIONS[int(raw.argmax())]
                predictions.append(action)
                labels.append(row["model_label"])
                scenarios.append(action in ALLOWED_ACTIONS[row["Intent"]])
                conflicts.append(bool(conflict_reasons(row, "Reduce" if action == "Decrease" else action)))
            accuracy = statistics_mean([prediction == label for prediction, label in zip(predictions, labels)])
            scenario = statistics_mean(scenarios)
            non_conflict = 1 - statistics_mean(conflicts)
            return non_conflict, scenario, accuracy, -sum(parameters.__dict__.values())

        return max(candidates, key=quality)

    def _fit_temperature(self) -> float:
        logits, labels = [], []
        for row in self.validation.to_dict("records"):
            raw, *_ = self._score(row, self.default_rules, row["Intent"], "full", self.scoring)
            logits.append(raw)
            labels.append(ACTIONS.index(row["model_label"]))
        return fit_temperature(logits, labels)

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
        temperature = 1 if ablation in {"without_calibration", "backbone"} else self.temperature
        ranked = rank_actions(raw, temperature)
        selected, confidence = str(ranked[0]["action"]), float(ranked[0]["score"])
        performance = float(sum(probabilities[index] * (.90, .55, .25, .45)[index] for index in range(4)))
        activated = [item for item in rule_results if item["action"] == selected and item["triggered"]]
        explanation = explain(selected, confidence, intent, attribution, channels, activated)
        return EngineResult(
            selected, confidence, float(raw_probabilities[ACTIONS.index(selected)]), performance,
            "High" if confidence >= .75 else "Medium" if confidence >= .50 else "Low",
            ranked, attribution, channels, rule_results, explanation,
            (time.perf_counter() - started) * 1000,
        )


def statistics_mean(values: list[Any], default: float = 0.0) -> float:
    return float(np.mean(values)) if values else default
