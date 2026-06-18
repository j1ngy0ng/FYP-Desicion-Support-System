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
from dataclasses import dataclass
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

INTENT_SCENARIO_ACTIONS = {
    "Survival": {"Reduce", "Maintain", "Investigate"},
    "Retention": {"Maintain", "Increase", "Investigate"},
    "Growth": {"Increase", "Maintain"},
}

ACTIONABILITY_WEIGHTS = {"scenario_fit": 0.45, "non_conflict": 0.35, "confidence": 0.20}
USER_ACCEPTANCE_WEIGHTS = {"actionability": 0.40, "trust_alignment": 0.35, "explanation_usefulness": 0.25}
NON_ATTRIBUTION_EXPLANATION_FACTOR = 0.35


@dataclass
class BaselineResult:
    name: str
    predictions: List[str]
    confidences: List[float]
    explanations: List[str]
    latency_ms: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline systems and compute evaluation metrics.")
    parser.add_argument("--dataset", default="Dataset.csv", help="Path to Dataset.csv")
    parser.add_argument("--output-dir", default="outputs/baseline_evaluation", help="Output directory")
    parser.add_argument("--test-size", type=float, default=0.2, help="Holdout test ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--ece-bins", type=int, default=10, help="ECE bins")
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
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
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
        reviewer_1 = canonical_action(item.get("Reviewer_1_Label", ""))
        reviewer_2 = canonical_action(item.get("Reviewer_2_Label", ""))
        reference = canonical_action(item.get("Reference_Action", ""))
        item["label"] = reviewer_1 if reviewer_1 and reviewer_1 == reviewer_2 else reference
        item["Reference_Action"] = reference
        item["Intent"] = item.get("Intent", "").strip().title()
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
        cut = max(1, int(round(len(group_rows) * test_size)))
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
    preds, confs, exps = [], [], []
    start = time.perf_counter()
    for row in rows:
        roi = row["ROI"]
        conv = row["conversion_rate"]
        engagement = row["Engagement_Score"]
        score_reduce = 0.9 * max(0.0, -roi) + 1.2 * max(0.0, 0.08 - conv)
        score_increase = 0.8 * max(0.0, roi - 1.8) + 1.1 * max(0.0, conv - 0.2) + 0.02 * engagement
        score_maintain = 1.0 - min(1.0, abs(roi - 1.0) / 2.0) + max(0.0, 0.18 - abs(conv - 0.15))
        score_investigate = 0.25 if (0.05 <= conv <= 0.12 and 0.2 <= roi <= 0.9) else 0.0
        actions = ["Reduce", "Maintain", "Increase", "Investigate"]
        scores = [score_reduce, score_maintain, score_increase, score_investigate]
        probs = softmax(scores)
        idx = max(range(len(actions)), key=lambda i: probs[i])
        preds.append(actions[idx])
        confs.append(probs[idx])
        exps.append("")
    latency = (time.perf_counter() - start) * 1000 / max(1, len(rows))
    return BaselineResult("Baseline A - Heuristic Scorecard", preds, confs, exps, latency)


def fit_centroid_model(train_rows: List[dict]) -> Tuple[List[str], Dict[str, List[float]], List[float], List[float]]:
    labels = sorted({row["label"] for row in train_rows})
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
    preds, confs, exps = [], [], []
    start = time.perf_counter()
    for row in test_rows:
        probs = predict_centroid_proba(row, labels, centroids, means, stds)
        pred = max(probs, key=probs.get)
        preds.append(pred)
        confs.append(probs[pred])
        exps.append("")
    latency = (time.perf_counter() - start) * 1000 / max(1, len(test_rows))
    return BaselineResult("Baseline B - Predictive Analytics Only", preds, confs, exps, latency)


def baseline_c_predict(test_rows: List[dict], model, channel_attr: Dict[str, float]) -> BaselineResult:
    labels, centroids, means, stds = model
    preds, confs, exps = [], [], []
    start = time.perf_counter()
    for row in test_rows:
        probs = predict_centroid_proba(row, labels, centroids, means, stds)
        logits = {label: math.log(max(p, 1e-9)) for label, p in probs.items()}
        ch_values = [channel_attr[ch] for ch in row["channels"] if ch in channel_attr]
        attr_strength = statistics.fmean(ch_values) if ch_values else 0.5
        logits["Increase"] = logits.get("Increase", -20) + (attr_strength - 0.5) * 1.3
        logits["Reduce"] = logits.get("Reduce", -20) + (0.5 - attr_strength) * 1.3
        logits["Maintain"] = logits.get("Maintain", -20) + (0.6 - abs(attr_strength - 0.5)) * 0.35
        keys = sorted(logits.keys())
        values = softmax([logits[k] for k in keys])
        adj_probs = {k: values[i] for i, k in enumerate(keys)}
        pred = max(adj_probs, key=adj_probs.get)
        preds.append(pred)
        confs.append(adj_probs[pred])
        exps.append(
            f"Attribution-adjusted recommendation from channels {', '.join(row['channels']) or 'N/A'} "
            f"(strength={attr_strength:.2f})."
        )
    latency = (time.perf_counter() - start) * 1000 / max(1, len(test_rows))
    return BaselineResult("Baseline C - Predictive Analytics with Attribution", preds, confs, exps, latency)


def recommendation_accuracy(preds: Sequence[str], labels: Sequence[str]) -> float:
    if not labels:
        return 0.0
    hits = sum(1 for p, y in zip(preds, labels) if p == y)
    return hits / len(labels)


def scenario_fit_rate(preds: Sequence[str], intents: Sequence[str]) -> float:
    hits = 0
    for pred, intent in zip(preds, intents):
        allowed = INTENT_SCENARIO_ACTIONS.get(intent, {"Increase", "Maintain", "Reduce", "Investigate"})
        if pred in allowed:
            hits += 1
    return hits / max(1, len(preds))


def row_has_conflict(row: dict, action: str) -> bool:
    roi = row["ROI"]
    conv = row["conversion_rate"]
    intent = row["Intent"]
    conflict_rules = [
        action == "Increase" and roi < 0,
        action == "Increase" and conv < 0.08,
        action == "Reduce" and roi > 2.0 and conv > 0.2,
        intent == "Growth" and action == "Reduce",
    ]
    return any(conflict_rules)


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
    if "Baseline C" in baseline_name:
        return avg
    return avg * NON_ATTRIBUTION_EXPLANATION_FACTOR


def human_metrics(
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
        "Recommendation Actionability": actionability,
        "Trust Alignment": trust_alignment,
        "Explanation Usefulness": explanation,
        "User Acceptance": user_acceptance,
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
        "Scenario-Fit Rate": scenario_fit_rate(preds, intents),
        "Logical Conflict Rate": logical_conflict_rate(rows, preds),
        "Expected Calibration Error (ECE)": expected_calibration_error(confidences, correctness, bins),
        "Recommendation Latency (ms)": baseline.latency_ms,
    }
    metrics.update(human_metrics(rows, preds, confidences, labels, baseline.explanations, baseline.name))
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
        headers.extend([f"{prefix}_Prediction", f"{prefix}_Confidence"])
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for i, row in enumerate(rows):
            record = [row.get("Campaign_ID", ""), row["Intent"], labels[i], row["Reference_Action"]]
            for b in baseline_results:
                record.extend([b.predictions[i], f"{b.confidences[i]:.6f}"])
            writer.writerow(record)


def save_metrics(path: Path, baseline_metrics: Dict[str, Dict[str, float]]) -> None:
    metric_names = list(next(iter(baseline_metrics.values())).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Baseline", *metric_names])
        for baseline_name, metrics in baseline_metrics.items():
            writer.writerow([baseline_name, *[f"{metrics[m]:.6f}" for m in metric_names]])


def save_markdown(path: Path, baseline_metrics: Dict[str, Dict[str, float]]) -> None:
    metric_names = list(next(iter(baseline_metrics.values())).keys())
    lines = [
        "# Baseline Comparison Metrics",
        "",
        "This table is generated from `Dataset.csv` using Chapter 3 baseline configurations and metrics.",
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
            "- Baseline A: heuristic scorecard (manual threshold logic).",
            "- Baseline B: predictive-only centroid classifier.",
            "- Baseline C: predictive + channel attribution adjustment.",
            "- Human metrics are computed as reproducible proxy scores from model outputs for comparison-table preparation.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = load_dataset(dataset_path)
    train_rows, test_rows = stratified_split(rows, args.test_size, args.seed)
    labels = [row["label"] for row in test_rows]

    model = fit_centroid_model(train_rows)
    channel_attr = build_channel_attribution(train_rows)

    baseline_a = baseline_a_predict(test_rows)
    baseline_b = baseline_b_predict(test_rows, model)
    baseline_c = baseline_c_predict(test_rows, model, channel_attr)
    baseline_results = [baseline_a, baseline_b, baseline_c]

    baseline_metrics = {
        b.name: evaluate_baseline(b, test_rows, labels, args.ece_bins) for b in baseline_results
    }

    save_predictions(output_dir / "baseline_predictions.csv", test_rows, baseline_results, labels)
    save_metrics(output_dir / "baseline_metrics.csv", baseline_metrics)
    save_markdown(output_dir / "comparison_table.md", baseline_metrics)

    print(f"Saved outputs to: {output_dir.resolve()}")
    for name, metrics in baseline_metrics.items():
        print(f"\n{name}")
        for key, value in metrics.items():
            print(f"  - {key}: {value:.4f}")


if __name__ == "__main__":
    main()
