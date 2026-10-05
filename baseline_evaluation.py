#!/usr/bin/env python3
"""Baseline systems and evaluation metrics generator for Chapter 3."""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


NUMERIC_FIELDS = [
    "Duration",
    "Impressions",
    "Clicks",
    "Leads",
    "Conversions",
    "Revenue",
    "Acquisition_Cost",
    "ROI",
    "Engagement_Score",
]

ACTION_ALIASES = {
    "increase": "Increase",
    "maintain": "Maintain",
    "reduce": "Reduce",
    "decrease": "Reduce",
    "investigate": "Investigate",
}

# Canonical index mapping used by every baseline probability vector, ranking,
# export and metric: 0=Increase, 1=Maintain, 2=Reduce, 3=Investigate.
ACTION_ORDER = ("Increase", "Maintain", "Reduce", "Investigate")
ACTION_INDEX = {action: index for index, action in enumerate(ACTION_ORDER)}


def assert_canonical_action_order(actions: Sequence[str]) -> None:
    if tuple(actions) != ACTION_ORDER:
        raise ValueError(f"Action order must be {ACTION_ORDER}, got {tuple(actions)}")


def rank_actions(probabilities: Dict[str, float]) -> List[str]:
    return sorted(
        probabilities,
        key=lambda action: (-probabilities[action], ACTION_INDEX[action]),
    )

INTENT_SCENARIO_ACTIONS = {
    "Survival": {"Reduce", "Maintain", "Investigate"},
    "Retention": {"Maintain", "Increase", "Investigate"},
    "Growth": {"Increase", "Maintain", "Investigate"},
}

ACTIONABILITY_WEIGHTS = {"scenario_fit": 0.45, "non_conflict": 0.35, "confidence": 0.20}
USER_ACCEPTANCE_WEIGHTS = {"actionability": 0.40, "trust_alignment": 0.35, "explanation_usefulness": 0.25}
NON_ATTRIBUTION_EXPLANATION_FACTOR = 0.35

# Predefined domain thresholds used by the logical-conflict catalogue. These
# values are fixed for every evaluated system; they are not fitted to a
# baseline's predictions.
LOW_ROI = 0.0
HIGH_ROI = 2.0
VERY_HIGH_ROI = 4.0
LOW_CONVERSION_RATE = 0.08
HIGH_CONVERSION_RATE = 0.20
LOW_CTR = 0.03
HIGH_CTR = 0.10
LOW_ENGAGEMENT = 5.0
HIGH_ENGAGEMENT = 20.0
MIN_DECISION_CLICKS = 500.0
MIN_DECISION_CONVERSIONS = 50.0


@dataclass
class BaselineResult:
    name: str
    predictions: List[str]
    confidences: List[float]
    explanations: List[str]
    latency_ms: float
    top2_predictions: List[List[str]] = field(default_factory=list)
    case_latencies_ms: List[float] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline systems and compute evaluation metrics.")
    parser.add_argument(
        "--dataset",
        default="data/benchmark_audited.csv",
        help="Completed human-audited benchmark path",
    )
    parser.add_argument(
        "--train-dataset",
        help="Optional training dataset. Use the normal dataset here when testing robustness on stress data.",
    )
    parser.add_argument("--output-dir", default="outputs/normal", help="Output directory")
    parser.add_argument("--test-size", type=float, default=0.2, help="Holdout test ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--ece-bins", type=int, default=5, help="ECE bins")
    return parser.parse_args()


def canonical_action(action: str) -> str:
    return ACTION_ALIASES.get(action.strip().lower(), action.strip().title())


def parse_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def split_channels(channel_value: str) -> List[str]:
    return [token.strip().lower() for token in channel_value.split(",") if token.strip()]


def load_dataset(path: Path) -> List[dict]:
    if not path.exists():
        raise ValueError(
            f"{path} does not exist. Complete the human annotation protocol first."
        )
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    forbidden = {
        "Intent",
        "Reference_Action",
        "Justification",
        "Reviewer_1_Label",
        "Reviewer_2_Label",
    }
    legacy = sorted(forbidden.intersection(rows[0] if rows else {}))
    if legacy:
        raise ValueError(
            "Legacy AI-generated annotation columns are forbidden: "
            + ", ".join(legacy)
        )
    required = {
        "Reviewer_1_Intent",
        "Reviewer_1_Action",
        "Reviewer_2_Intent",
        "Reviewer_2_Action",
        "Adjudicated_Intent",
        "Adjudicated_Action",
        "Annotation_Status",
    }
    missing = sorted(required.difference(rows[0] if rows else {}))
    if missing:
        raise ValueError("Audited benchmark is missing columns: " + ", ".join(missing))
    if len(rows) < 120:
        raise ValueError("The frozen audited benchmark must contain at least 120 cases.")
    if any(row["Annotation_Status"].strip() != "Audited" for row in rows):
        raise ValueError("Every benchmark case must have Annotation_Status=Audited.")
    prepared = []
    for row in rows:
        item = dict(row)
        for key in NUMERIC_FIELDS:
            item[key] = parse_float(item.get(key, "0"))
        clicks = item["Clicks"]
        impressions = item["Impressions"]
        conversions = item["Conversions"]
        leads = item["Leads"]
        item["ctr"] = clicks / impressions if impressions > 0 else 0.0
        item["conversion_rate"] = conversions / clicks if clicks > 0 else 0.0
        item["lead_to_conversion"] = conversions / leads if leads > 0 else 0.0
        item["cost_per_conversion"] = item["Acquisition_Cost"] / conversions if conversions > 0 else item["Acquisition_Cost"]
        reviewer_1 = canonical_action(item["Reviewer_1_Action"])
        reviewer_2 = canonical_action(item["Reviewer_2_Action"])
        reference = canonical_action(item["Adjudicated_Action"])
        if reviewer_1 not in ACTION_ALIASES.values() or reviewer_2 not in ACTION_ALIASES.values():
            raise ValueError("Reviewer actions must use the four-action rubric.")
        if reference not in ACTION_ALIASES.values():
            raise ValueError("Adjudicated actions must use the four-action rubric.")
        item["label"] = reference
        item["Reference_Action"] = reference
        item["Intent"] = item["Adjudicated_Intent"].strip().title()
        if item["Intent"] not in INTENT_SCENARIO_ACTIONS:
            raise ValueError("Adjudicated intents must be Survival, Retention or Growth.")
        item["channels"] = split_channels(item.get("Channel_Used", ""))
        prepared.append(item)
    return prepared


def stratified_split(rows: List[dict], test_size: float, seed: int) -> Tuple[List[dict], List[dict]]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[row["label"]].append(row)
    rng = random.Random(seed)
    train, test = [], []
    for group_rows in groups.values():
        rng.shuffle(group_rows)
        # A singleton class cannot be evaluated meaningfully and must remain
        # available to the training set instead of being removed from it.
        cut = 0 if len(group_rows) < 2 else max(1, int(round(len(group_rows) * test_size)))
        test.extend(group_rows[:cut])
        train.extend(group_rows[cut:])
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def get_feature_vector(row: dict) -> List[float]:
    return [
        row["Duration"],
        row["Impressions"],
        row["Clicks"],
        row["Leads"],
        row["Conversions"],
        row["Revenue"],
        row["Acquisition_Cost"],
        row["ROI"],
        row["Engagement_Score"],
        row["ctr"],
        row["conversion_rate"],
        row["lead_to_conversion"],
        row["cost_per_conversion"],
    ]


def fit_scaler(train_vectors: List[List[float]]) -> Tuple[List[float], List[float]]:
    dims = len(train_vectors[0])
    means = []
    stds = []
    for i in range(dims):
        values = [vector[i] for vector in train_vectors]
        mean = statistics.fmean(values)
        std = statistics.pstdev(values) or 1.0
        means.append(mean)
        stds.append(std)
    return means, stds


def scale_vector(vector: List[float], means: List[float], stds: List[float]) -> List[float]:
    return [(value - means[i]) / stds[i] for i, value in enumerate(vector)]


def softmax(logits: Sequence[float]) -> List[float]:
    peak = max(logits)
    exps = [math.exp(x - peak) for x in logits]
    denom = sum(exps)
    return [x / denom for x in exps]


def baseline_a_predict(rows: List[dict]) -> BaselineResult:
    preds, confs, exps, top2, case_latencies = [], [], [], [], []
    start = time.perf_counter()
    for row in rows:
        case_started = time.perf_counter()
        roi = row["ROI"]
        conv = row["conversion_rate"]
        engagement = row["Engagement_Score"]
        score_reduce = 0.9 * max(0.0, -roi) + 1.2 * max(0.0, 0.08 - conv)
        score_increase = 0.8 * max(0.0, roi - 1.8) + 1.1 * max(0.0, conv - 0.2) + 0.02 * engagement
        score_maintain = 1.0 - min(1.0, abs(roi - 1.0) / 2.0) + max(0.0, 0.18 - abs(conv - 0.15))
        score_investigate = 0.25 if (0.05 <= conv <= 0.12 and 0.2 <= roi <= 0.9) else 0.0
        actions = ACTION_ORDER
        scores = [score_increase, score_maintain, score_reduce, score_investigate]
        probs = softmax(scores)
        idx = max(range(len(actions)), key=lambda i: probs[i])
        preds.append(actions[idx])
        confs.append(probs[idx])
        exps.append("")
        top2.append([
            actions[index]
            for index in sorted(range(len(actions)), key=lambda i: probs[i], reverse=True)[:2]
        ])
        case_latencies.append((time.perf_counter() - case_started) * 1000)
    latency = (time.perf_counter() - start) * 1000 / max(1, len(rows))
    return BaselineResult(
        "B1: Heuristic Scorecard", preds, confs, exps, latency,
        top2, case_latencies,
    )


def intent_only_predict(rows: List[dict]) -> BaselineResult:
    """Fixed intent-to-action comparator requested by the supervision review."""

    intent_action = {
        "Growth": "Increase",
        "Retention": "Maintain",
        "Survival": "Reduce",
    }
    started = time.perf_counter()
    predictions, confidences, explanations, top2, latencies = [], [], [], [], []
    for row in rows:
        case_started = time.perf_counter()
        action = intent_action[row["Intent"]]
        alternatives = [item for item in ACTION_ORDER if item != action]
        predictions.append(action)
        confidences.append(1.0)
        explanations.append(f"Fixed {row['Intent']} intent lookup selected {action}.")
        top2.append([action, alternatives[0]])
        latencies.append((time.perf_counter() - case_started) * 1000)
    return BaselineResult(
        "Supervisor Baseline - Intent-Only Deterministic",
        predictions,
        confidences,
        explanations,
        (time.perf_counter() - started) * 1000 / max(1, len(rows)),
        top2,
        latencies,
    )


def weighted_deterministic_predict(rows: List[dict]) -> BaselineResult:
    """Fixed intent, performance and safeguard score without learned parameters."""

    intent_scores = {
        "Growth": {"Increase": 1.0, "Maintain": .5, "Reduce": 0.0, "Investigate": .15},
        "Retention": {"Increase": .4, "Maintain": 1.0, "Reduce": 0.0, "Investigate": .15},
        "Survival": {"Increase": 0.0, "Maintain": .5, "Reduce": 1.0, "Investigate": .2},
    }
    started = time.perf_counter()
    predictions, confidences, explanations, top2, latencies = [], [], [], [], []
    for row in rows:
        case_started = time.perf_counter()
        scores = dict(intent_scores[row["Intent"]])
        strong = (
            (row["ROI"] >= HIGH_ROI),
            (row["conversion_rate"] >= HIGH_CONVERSION_RATE),
            (row["ctr"] >= HIGH_CTR),
            (row["Engagement_Score"] >= HIGH_ENGAGEMENT),
        )
        weak = (
            (row["ROI"] < LOW_ROI),
            (row["conversion_rate"] < LOW_CONVERSION_RATE),
            (row["ctr"] < LOW_CTR),
            (row["Engagement_Score"] < LOW_ENGAGEMENT),
        )
        scores["Increase"] += sum(strong) * .25
        scores["Reduce"] += sum(weak) * .25
        if row["Clicks"] < MIN_DECISION_CLICKS or row["Conversions"] < MIN_DECISION_CONVERSIONS:
            scores["Investigate"] += .6
        conflict_count = 0
        for action in ACTION_ORDER:
            conflicts = conflict_reasons(row, action)
            conflict_count += len(conflicts)
            scores[action] -= .45 * len(conflicts)
        if conflict_count:
            scores["Investigate"] += .15
        probabilities = dict(zip(ACTION_ORDER, softmax([scores[action] for action in ACTION_ORDER])))
        ranked = rank_actions(probabilities)
        predictions.append(ranked[0])
        confidences.append(probabilities[ranked[0]])
        explanations.append(
            "Fixed weighted score combined declared intent, performance thresholds, "
            f"evidence sufficiency and {conflict_count} safeguard conflict(s)."
        )
        top2.append(ranked[:2])
        latencies.append((time.perf_counter() - case_started) * 1000)
    return BaselineResult(
        "Supervisor Baseline - Weighted Deterministic",
        predictions,
        confidences,
        explanations,
        (time.perf_counter() - started) * 1000 / max(1, len(rows)),
        top2,
        latencies,
    )


def fit_centroid_model(train_rows: List[dict]) -> Tuple[List[str], Dict[str, List[float]], List[float], List[float]]:
    observed = {row["label"] for row in train_rows}
    labels = [action for action in ACTION_ORDER if action in observed]
    assert_canonical_action_order(labels)
    vectors = [get_feature_vector(r) for r in train_rows]
    means, stds = fit_scaler(vectors)
    class_vectors: Dict[str, List[List[float]]] = defaultdict(list)
    for row in train_rows:
        class_vectors[row["label"]].append(scale_vector(get_feature_vector(row), means, stds))
    centroids: Dict[str, List[float]] = {}
    for label in labels:
        samples = class_vectors[label]
        centroids[label] = [statistics.fmean([v[i] for v in samples]) for i in range(len(samples[0]))]
    return labels, centroids, means, stds


def predict_centroid_proba(
    row: dict,
    labels: List[str],
    centroids: Dict[str, List[float]],
    means: List[float],
    stds: List[float],
) -> Dict[str, float]:
    vector = scale_vector(get_feature_vector(row), means, stds)
    logits = []
    for label in labels:
        centroid = centroids[label]
        distance = math.sqrt(sum((vector[i] - centroid[i]) ** 2 for i in range(len(vector))))
        logits.append(-distance)
    probs = softmax(logits)
    return {label: probs[i] for i, label in enumerate(labels)}


def build_channel_attribution(train_rows: List[dict]) -> Dict[str, float]:
    channel_scores: Dict[str, List[float]] = defaultdict(list)
    for row in train_rows:
        score = (row["ROI"] * 0.7) + (row["conversion_rate"] * 8.0)
        for ch in row["channels"]:
            channel_scores[ch].append(score)
    averaged = {ch: statistics.fmean(values) for ch, values in channel_scores.items()}
    if not averaged:
        return {}
    values = list(averaged.values())
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    return {ch: (value - lo) / span for ch, value in averaged.items()}


def baseline_b_predict(test_rows: List[dict], model) -> BaselineResult:
    labels, centroids, means, stds = model
    preds, confs, exps, top2, case_latencies = [], [], [], [], []
    start = time.perf_counter()
    for row in test_rows:
        case_started = time.perf_counter()
        probs = predict_centroid_proba(row, labels, centroids, means, stds)
        ranked = rank_actions(probs)
        pred = ranked[0]
        preds.append(pred)
        confs.append(probs[pred])
        exps.append("")
        top2.append(ranked[:2])
        case_latencies.append((time.perf_counter() - case_started) * 1000)
    latency = (time.perf_counter() - start) * 1000 / max(1, len(test_rows))
    return BaselineResult(
        "B2: Predictive Only", preds, confs, exps, latency,
        top2, case_latencies,
    )


def baseline_c_predict(test_rows: List[dict], model, channel_attr: Dict[str, float]) -> BaselineResult:
    labels, centroids, means, stds = model
    preds, confs, exps, top2, case_latencies = [], [], [], [], []
    start = time.perf_counter()
    for row in test_rows:
        case_started = time.perf_counter()
        probs = predict_centroid_proba(row, labels, centroids, means, stds)
        logits = {label: math.log(max(p, 1e-9)) for label, p in probs.items()}
        ch_values = [channel_attr[ch] for ch in row["channels"] if ch in channel_attr]
        attr_strength = statistics.fmean(ch_values) if ch_values else 0.5
        logits["Increase"] = logits.get("Increase", -20) + (attr_strength - 0.5) * 1.3
        logits["Reduce"] = logits.get("Reduce", -20) + (0.5 - attr_strength) * 1.3
        logits["Maintain"] = logits.get("Maintain", -20) + (0.6 - abs(attr_strength - 0.5)) * 0.35
        keys = [action for action in ACTION_ORDER if action in logits]
        values = softmax([logits[k] for k in keys])
        adj_probs = {k: values[i] for i, k in enumerate(keys)}
        ranked = rank_actions(adj_probs)
        pred = ranked[0]
        preds.append(pred)
        confs.append(adj_probs[pred])
        top2.append(ranked[:2])
        exps.append(
            f"Channel-evidence-adjusted recommendation from channels {', '.join(row['channels']) or 'N/A'} "
            f"(strength={attr_strength:.2f})."
        )
        case_latencies.append((time.perf_counter() - case_started) * 1000)
    latency = (time.perf_counter() - start) * 1000 / max(1, len(test_rows))
    return BaselineResult(
        "B3: Predictive plus Channel Evidence", preds, confs, exps,
        latency, top2, case_latencies,
    )


def filter_conflicting_actions(row: dict, probabilities: Dict[str, float]) -> Tuple[str, float, List[str]]:
    rejected = [action for action in probabilities if conflict_reasons(row, action)]
    allowed = {action: probability for action, probability in probabilities.items() if action not in rejected}
    if not allowed:
        return "Investigate", 1.0, rejected
    total = sum(allowed.values())
    adjusted = {action: probability / total for action, probability in allowed.items()}
    action = rank_actions(adjusted)[0]
    return action, adjusted[action], rejected


def baseline_d_predict(test_rows: List[dict], model) -> BaselineResult:
    labels, centroids, means, stds = model
    preds, confs, exps, top2, case_latencies = [], [], [], [], []
    start = time.perf_counter()
    for row in test_rows:
        case_started = time.perf_counter()
        probabilities = predict_centroid_proba(row, labels, centroids, means, stds)
        pred, confidence, rejected = filter_conflicting_actions(row, probabilities)
        preds.append(pred)
        confs.append(confidence)
        exps.append(
            f"Post-hoc rules filtered {', '.join(rejected) or 'no actions'} after predictive scoring."
        )
        allowed = {
            action: probability
            for action, probability in probabilities.items()
            if action not in rejected
        }
        top2.append(
            rank_actions(allowed)[:2]
            or ["Investigate"]
        )
        case_latencies.append((time.perf_counter() - case_started) * 1000)
    latency = (time.perf_counter() - start) * 1000 / max(1, len(test_rows))
    return BaselineResult(
        "Post-hoc Hard-Rule Filter", preds, confs, exps, latency,
        top2, case_latencies,
    )


def recommendation_accuracy(preds: Sequence[str], labels: Sequence[str]) -> float:
    if not labels:
        return 0.0
    hits = sum(1 for p, y in zip(preds, labels) if p == y)
    return hits / len(labels)


def macro_f1_score(preds: Sequence[str], labels: Sequence[str]) -> float:
    observed = set(labels) | set(preds)
    classes = [action for action in ACTION_ORDER if action in observed]
    scores = []
    for label in classes:
        true_positive = sum(
            prediction == label and reference == label
            for prediction, reference in zip(preds, labels)
        )
        false_positive = sum(
            prediction == label and reference != label
            for prediction, reference in zip(preds, labels)
        )
        false_negative = sum(
            prediction != label and reference == label
            for prediction, reference in zip(preds, labels)
        )
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(0.0 if denominator == 0 else 2 * true_positive / denominator)
    return statistics.fmean(scores) if scores else 0.0


def top2_agreement(
    top2_predictions: Sequence[Sequence[str]],
    labels: Sequence[str],
    fallback_predictions: Sequence[str],
) -> float:
    ranked = top2_predictions or [[prediction] for prediction in fallback_predictions]
    return sum(
        reference in predictions
        for predictions, reference in zip(ranked, labels)
    ) / max(1, len(labels))


def percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def scenario_fit_rate(preds: Sequence[str], intents: Sequence[str]) -> float:
    hits = 0
    for pred, intent in zip(preds, intents):
        allowed = INTENT_SCENARIO_ACTIONS.get(intent, {"Increase", "Maintain", "Reduce", "Investigate"})
        if pred in allowed:
            hits += 1
    return hits / max(1, len(preds))


def conflict_reasons(row: dict, action: str) -> List[str]:
    """Return all predefined logical contradictions for one recommendation."""

    roi = row["ROI"]
    conv = row["conversion_rate"]
    ctr = row["ctr"]
    engagement = row["Engagement_Score"]
    intent = row["Intent"]
    clicks = row["Clicks"]
    conversions = row["Conversions"]
    reasons = []

    # Intent-policy contradictions.
    if intent == "Growth" and action == "Reduce":
        reasons.append("intent:growth_recommended_reduce")
    if intent == "Survival" and action == "Increase":
        reasons.append("intent:survival_recommended_increase")
    if intent == "Retention" and action == "Reduce":
        reasons.append("intent:retention_recommended_reduce")

    # Recommendations that oppose individual performance signals.
    if action == "Increase" and roi < LOW_ROI:
        reasons.append("performance:increase_with_negative_roi")
    if action == "Increase" and conv < LOW_CONVERSION_RATE:
        reasons.append("performance:increase_with_low_conversion")
    if action == "Increase" and ctr < LOW_CTR:
        reasons.append("performance:increase_with_low_ctr")
    if action == "Increase" and engagement < LOW_ENGAGEMENT:
        reasons.append("performance:increase_with_low_engagement")

    strong_signals = sum(
        [
            roi > HIGH_ROI,
            conv > HIGH_CONVERSION_RATE,
            ctr > HIGH_CTR,
            engagement > HIGH_ENGAGEMENT,
        ]
    )
    if action == "Reduce" and strong_signals >= 2:
        reasons.append("performance:reduce_despite_multiple_strong_signals")

    # A neutral recommendation is contradictory only when all core signals are
    # exceptionally strong; this avoids treating ordinary caution as conflict.
    if (
        action == "Maintain"
        and roi > VERY_HIGH_ROI
        and conv > HIGH_CONVERSION_RATE
        and ctr > HIGH_CTR
        and engagement > HIGH_ENGAGEMENT
    ):
        reasons.append("performance:maintain_despite_exceptional_performance")

    # Escalation/reduction without enough response evidence should be investigated.
    if action in {"Increase", "Reduce"} and (
        clicks < MIN_DECISION_CLICKS or conversions < MIN_DECISION_CONVERSIONS
    ):
        reasons.append("evidence:decisive_action_with_insufficient_sample")

    return reasons


def row_has_conflict(row: dict, action: str) -> bool:
    return bool(conflict_reasons(row, action))


def logical_conflict_rate(rows: Sequence[dict], preds: Sequence[str]) -> float:
    conflicts = sum(1 for row, pred in zip(rows, preds) if row_has_conflict(row, pred))
    return conflicts / max(1, len(preds))


def expected_calibration_error(confidences: Sequence[float], correct: Sequence[int], bins: int = 10) -> float:
    if not confidences:
        return 0.0
    ece = 0.0
    n = len(confidences)
    for b in range(bins):
        lo = b / bins
        hi = (b + 1) / bins
        is_last_bin = b == bins - 1
        idx = [i for i, c in enumerate(confidences) if lo <= c < hi or (is_last_bin and c == 1.0)]
        if not idx:
            continue
        bin_conf = statistics.fmean([confidences[i] for i in idx])
        bin_acc = statistics.fmean([correct[i] for i in idx])
        ece += (len(idx) / n) * abs(bin_acc - bin_conf)
    return ece


def explanation_usefulness_score(explanations: Sequence[str], baseline_name: str) -> float:
    if not explanations:
        return 0.0
    richness = []
    for text in explanations:
        t = text.lower()
        score = 0.0
        if len(text.split()) >= 8:
            score += 0.35
        if "channel" in t or "attribution" in t:
            score += 0.3
        if "strength" in t or "confidence" in t:
            score += 0.35
        richness.append(min(1.0, score))
    avg = statistics.fmean(richness)
    if "B3:" in baseline_name or "Proposed" in baseline_name:
        return avg
    return avg * NON_ATTRIBUTION_EXPLANATION_FACTOR


def proxy_metrics(
    rows: Sequence[dict],
    preds: Sequence[str],
    confidences: Sequence[float],
    labels: Sequence[str],
    explanations: Sequence[str],
    baseline_name: str,
) -> Dict[str, float]:
    correctness = [1 if p == y else 0 for p, y in zip(preds, labels)]
    scenario = scenario_fit_rate(preds, [row["Intent"] for row in rows])
    non_conflict = 1.0 - logical_conflict_rate(rows, preds)
    actionability = max(
        0.0,
        min(
            1.0,
            ACTIONABILITY_WEIGHTS["scenario_fit"] * scenario
            + ACTIONABILITY_WEIGHTS["non_conflict"] * non_conflict
            + ACTIONABILITY_WEIGHTS["confidence"] * statistics.fmean(confidences),
        ),
    )
    trust_alignment = statistics.fmean([1.0 - abs(c - y) for c, y in zip(confidences, correctness)])
    explanation = explanation_usefulness_score(explanations, baseline_name)
    user_acceptance = max(
        0.0,
        min(
            1.0,
            USER_ACCEPTANCE_WEIGHTS["actionability"] * actionability
            + USER_ACCEPTANCE_WEIGHTS["trust_alignment"] * trust_alignment
            + USER_ACCEPTANCE_WEIGHTS["explanation_usefulness"] * explanation,
        ),
    )
    return {
        "Actionability Proxy": actionability,
        "Trust Alignment Proxy": trust_alignment,
        "Explanation Usefulness Proxy": explanation,
        "User Acceptance Proxy": user_acceptance,
    }


def evaluate_baseline(
    baseline: BaselineResult,
    rows: Sequence[dict],
    labels: Sequence[str],
    bins: int,
) -> Dict[str, float]:
    preds = baseline.predictions
    confidences = baseline.confidences
    intents = [row["Intent"] for row in rows]
    correctness = [1 if p == y else 0 for p, y in zip(preds, labels)]
    metrics = {
        "Recommendation Accuracy": recommendation_accuracy(preds, labels),
        "Macro F1": macro_f1_score(preds, labels),
        "Top-2 Agreement": top2_agreement(
            baseline.top2_predictions, labels, preds,
        ),
        "Scenario-Fit Rate": scenario_fit_rate(preds, intents),
        "Logical Conflict Rate": logical_conflict_rate(rows, preds),
        "Expected Calibration Error (ECE)": expected_calibration_error(confidences, correctness, bins),
        "Recommendation Latency (ms)": baseline.latency_ms,
        "P50 Latency (ms)": percentile(
            baseline.case_latencies_ms or [baseline.latency_ms], .50,
        ),
        "P95 Latency (ms)": percentile(
            baseline.case_latencies_ms or [baseline.latency_ms], .95,
        ),
    }
    metrics.update(proxy_metrics(rows, preds, confidences, labels, baseline.explanations, baseline.name))
    return metrics


def save_predictions(path: Path, rows: Sequence[dict], baseline_results: Sequence[BaselineResult], labels: Sequence[str]) -> None:
    headers = [
        "Campaign_ID",
        "Intent",
        "Ground_Truth_Label",
        "Reference_Action",
    ]
    for b in baseline_results:
        prefix = b.name.split(" - ")[0].replace(" ", "_")
        headers.extend(
            [
                f"{prefix}_Prediction",
                f"{prefix}_Confidence",
                f"{prefix}_Conflict",
                f"{prefix}_Conflict_Reasons",
            ]
        )
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(headers)
        for i, row in enumerate(rows):
            record = [row.get("Campaign_ID", ""), row["Intent"], labels[i], row["Reference_Action"]]
            for b in baseline_results:
                reasons = conflict_reasons(row, b.predictions[i])
                record.extend(
                    [
                        b.predictions[i],
                        f"{b.confidences[i]:.6f}",
                        int(bool(reasons)),
                        "; ".join(reasons),
                    ]
                )
            writer.writerow(record)


def save_metrics(path: Path, baseline_metrics: Dict[str, Dict[str, float]]) -> None:
    metric_names = list(next(iter(baseline_metrics.values())).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["Baseline", *metric_names])
        for baseline_name, metrics in baseline_metrics.items():
            writer.writerow([baseline_name, *[f"{metrics[m]:.6f}" for m in metric_names]])


def save_markdown(
    path: Path,
    baseline_metrics: Dict[str, Dict[str, float]],
    dataset_name: str,
) -> None:
    metric_names = list(next(iter(baseline_metrics.values())).keys())
    lines = [
        "# Baseline Comparison Metrics",
        "",
        f"This table is generated from `{dataset_name}` using Chapter 3 baseline configurations and metrics.",
        "",
        "|" + "Baseline|" + "|".join(metric_names) + "|",
        "|" + "---|" + "|".join(["---"] * len(metric_names)) + "|",
    ]
    for baseline_name, metrics in baseline_metrics.items():
        row = [baseline_name] + [f"{metrics[m]:.4f}" for m in metric_names]
        lines.append("|" + "|".join(row) + "|")
    lines.extend(
        [
            "",
            "## Notes",
            "- B1: heuristic scorecard (manual threshold logic).",
            "- B2: predictive-only centroid classifier.",
            "- B3: predictive plus training-derived campaign-level channel-evidence adjustment.",
            "- Post-hoc Hard-Rule Filter: predictive ranking followed by hard post-hoc conflict filtering.",
            "- Proxy metrics are deterministic technical indicators, not results from human participants.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = load_dataset(dataset_path)
    if args.train_dataset:
        train_rows, _ = stratified_split(load_dataset(Path(args.train_dataset)), args.test_size, args.seed)
        _, test_rows = stratified_split(rows, args.test_size, args.seed)
    else:
        train_rows, test_rows = stratified_split(rows, args.test_size, args.seed)
    labels = [row["label"] for row in test_rows]

    model = fit_centroid_model(train_rows)
    channel_attr = build_channel_attribution(train_rows)

    baseline_a = baseline_a_predict(test_rows)
    baseline_b = baseline_b_predict(test_rows, model)
    baseline_c = baseline_c_predict(test_rows, model, channel_attr)
    baseline_d = baseline_d_predict(test_rows, model)
    baseline_results = [baseline_a, baseline_b, baseline_c, baseline_d]

    baseline_metrics = {
        b.name: evaluate_baseline(b, test_rows, labels, args.ece_bins) for b in baseline_results
    }

    save_predictions(output_dir / "baseline_predictions.csv", test_rows, baseline_results, labels)
    save_metrics(output_dir / "baseline_metrics.csv", baseline_metrics)
    save_markdown(output_dir / "comparison_table.md", baseline_metrics, dataset_path.name)

    print(f"Saved outputs to: {output_dir.resolve()}")
    for name, metrics in baseline_metrics.items():
        print(f"\n{name}")
        for key, value in metrics.items():
            print(f"  - {key}: {value:.4f}")


if __name__ == "__main__":
    main()
