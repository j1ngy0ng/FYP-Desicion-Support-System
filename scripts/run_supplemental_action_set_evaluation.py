#!/usr/bin/env python3
"""Evaluate the frozen 50-case supplemental cohort against reviewed action sets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from baseline_evaluation import (
    ACTION_ORDER,
    BaselineResult,
    baseline_a_predict,
    baseline_b_predict,
    baseline_c_predict,
    baseline_d_predict,
    build_channel_attribution,
    expected_calibration_error,
    fit_centroid_model,
    intent_only_predict,
    logical_conflict_rate,
    macro_f1_score,
    majority_class_predict,
    percentile,
    scenario_fit_rate,
    weighted_deterministic_predict,
)
from scripts.run_confirmatory_evaluation import SEEDS, load_rows, proposed_predict, split_rows
from system_components.neuro_symbolic_reasoning_layer.engine import RecommendationEngine


SYSTEM_VARIANTS = {
    "B4: Integrated Learned Backbone": "backbone",
    "Unconstrained AI Baseline": "without_rules",
    "P: Full Proposed Method": "full",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("outputs/additional_test_review_20261022/additional_heldout_cases.csv"))
    parser.add_argument("--action-sets", type=Path, default=Path("outputs/additional_test_review_20261022/acceptable_action_sets_frozen.csv"))
    parser.add_argument("--benchmark", type=Path, default=Path("data/benchmark_audited.csv"))
    parser.add_argument("--training-dataset", type=Path, default=Path("data/layers/02_processed_model_data.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/additional_test_review_20261022/supplemental_evaluation"))
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def parse_set(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def load_supplemental_cases(case_path: Path, action_set_path: Path) -> list[dict]:
    with case_path.open(newline="", encoding="utf-8-sig") as handle:
        cases = list(csv.DictReader(handle))
    with action_set_path.open(newline="", encoding="utf-8-sig") as handle:
        action_sets = {row["Review_Case_ID"]: row for row in csv.DictReader(handle)}
    if len(cases) != 50 or len(action_sets) != 50:
        raise ValueError("The supplemental cohort and frozen action-set file must each contain exactly 50 cases.")
    rows = []
    numeric = ("Duration", "Impressions", "Clicks", "Leads", "Conversions", "Revenue", "Acquisition_Cost", "ROI", "Engagement_Score")
    for source in cases:
        case_id = source["Review_Case_ID"]
        reference = action_sets.get(case_id)
        if reference is None or reference["Campaign_ID"] != source["Campaign_ID"]:
            raise ValueError(f"Action-set alignment failed for {case_id}.")
        row = dict(source)
        for field in numeric:
            row[field] = float(row[field])
        row["ctr"] = row["Clicks"] / row["Impressions"] if row["Impressions"] else 0.0
        row["conversion_rate"] = row["Conversions"] / row["Clicks"] if row["Clicks"] else 0.0
        row["lead_to_conversion"] = row["Conversions"] / row["Leads"] if row["Leads"] else 0.0
        row["cost_per_conversion"] = row["Acquisition_Cost"] / row["Conversions"] if row["Conversions"] else row["Acquisition_Cost"]
        row["Intent"] = source["Assigned_Intent"].strip().title()
        row["label"] = reference["Preferred_Action"]
        row["Reference_Action"] = row["label"]
        row["acceptable"] = parse_set(reference["Acceptable_Actions"])
        row["conditional"] = parse_set(reference["Conditional_Actions"])
        row["admissible"] = parse_set(reference["Admissible_Actions"])
        row["unacceptable"] = parse_set(reference["Unacceptable_Actions"])
        row["channels"] = [value.strip().lower() for value in source["Channel_Used"].split(",") if value.strip()]
        if row["label"] not in row["admissible"]:
            raise ValueError(f"Preferred action is not admissible for {case_id}.")
        rows.append(row)
    if len({row["Campaign_ID"] for row in rows}) != 50:
        raise ValueError("Supplemental Campaign_ID values must be unique.")
    return rows


def set_metrics(result: BaselineResult, rows: list[dict]) -> dict[str, float]:
    predictions = result.predictions
    preferred = [row["label"] for row in rows]
    admissible_hits = [int(prediction in row["admissible"]) for prediction, row in zip(predictions, rows)]
    acceptable_hits = [int(prediction in row["acceptable"]) for prediction, row in zip(predictions, rows)]
    unacceptable_hits = [int(prediction in row["unacceptable"]) for prediction, row in zip(predictions, rows)]
    preferred_hits = [int(prediction == label) for prediction, label in zip(predictions, preferred)]
    top2 = result.top2_predictions or [[prediction] for prediction in predictions]
    return {
        "Preferred Exact Accuracy": statistics.fmean(preferred_hits),
        "Preferred Macro F1": macro_f1_score(predictions, preferred),
        "Strict Acceptable Rate": statistics.fmean(acceptable_hits),
        "Admissible Set Accuracy": statistics.fmean(admissible_hits),
        "Unacceptable Recommendation Rate": statistics.fmean(unacceptable_hits),
        "Top-2 Preferred Hit": statistics.fmean([int(label in ranked) for label, ranked in zip(preferred, top2)]),
        "Top-2 Admissible Hit": statistics.fmean([int(any(action in row["admissible"] for action in ranked)) for row, ranked in zip(rows, top2)]),
        "Scenario-Fit Rate": scenario_fit_rate(predictions, [row["Intent"] for row in rows]),
        "Rule-Catalogue Conflict Rate": logical_conflict_rate(rows, predictions),
        "ECE vs Preferred": expected_calibration_error(result.confidences, preferred_hits, 5),
        "ECE vs Admissible Set": expected_calibration_error(result.confidences, admissible_hits, 5),
        "P95 Latency (ms)": percentile(
            result.case_latencies_ms or [result.latency_ms], .95,
        ),
    }


def mean_metrics(results: list[BaselineResult], rows: list[dict]) -> dict[str, float]:
    runs = [set_metrics(result, rows) for result in results]
    return {metric: statistics.fmean(run[metric] for run in runs) for metric in runs[0]}


def bootstrap_intervals(results: list[BaselineResult], rows: list[dict], samples: int) -> dict[str, list[float]]:
    rng = random.Random(20261022)
    names = list(set_metrics(results[0], rows))
    observations = {name: [] for name in names}
    for _ in range(samples):
        indices = [rng.randrange(len(rows)) for _ in rows]
        sample_rows = [rows[index] for index in indices]
        for name in names:
            run_values = []
            for result in results:
                sampled = BaselineResult(
                    result.name,
                    [result.predictions[index] for index in indices],
                    [result.confidences[index] for index in indices],
                    [result.explanations[index] for index in indices],
                    result.latency_ms,
                    [result.top2_predictions[index] for index in indices],
                    [result.case_latencies_ms[index] for index in indices],
                )
                run_values.append(set_metrics(sampled, sample_rows)[name])
            observations[name].append(statistics.fmean(run_values))
    return {
        name: [
            sorted(values)[int(0.025 * (len(values) - 1))],
            sorted(values)[int(0.975 * (len(values) - 1))],
        ]
        for name, values in observations.items()
    }


def write_csv(path: Path, rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def reliability_rows(result: BaselineResult, rows: list[dict]) -> list[list[object]]:
    output = [["Bin", "Lower", "Upper", "Count", "Correct_Preferred", "Correct_Admissible", "Mean_Confidence", "Preferred_Accuracy", "Admissible_Accuracy", "Preferred_Gap", "Admissible_Gap"]]
    for index in range(5):
        lower, upper = index / 5, (index + 1) / 5
        positions = [i for i, confidence in enumerate(result.confidences) if lower <= confidence < upper or (index == 4 and confidence == 1.0)]
        preferred = [int(result.predictions[i] == rows[i]["label"]) for i in positions]
        admissible = [int(result.predictions[i] in rows[i]["admissible"]) for i in positions]
        mean_confidence = statistics.fmean(result.confidences[i] for i in positions) if positions else None
        preferred_accuracy = statistics.fmean(preferred) if positions else None
        admissible_accuracy = statistics.fmean(admissible) if positions else None
        output.append([
            index + 1, lower, upper, len(positions), sum(preferred), sum(admissible),
            "" if mean_confidence is None else f"{mean_confidence:.6f}",
            "" if preferred_accuracy is None else f"{preferred_accuracy:.6f}",
            "" if admissible_accuracy is None else f"{admissible_accuracy:.6f}",
            "" if mean_confidence is None else f"{abs(mean_confidence - preferred_accuracy):.6f}",
            "" if mean_confidence is None else f"{abs(mean_confidence - admissible_accuracy):.6f}",
        ])
    return output


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    supplemental = load_supplemental_cases(args.cases, args.action_sets)
    benchmark = load_rows(args.benchmark)
    train_rows, _, _ = split_rows(benchmark)
    training_campaigns = {row["Campaign_ID"] for row in train_rows}
    overlap = sorted(training_campaigns & {row["Campaign_ID"] for row in supplemental})
    if overlap:
        raise ValueError(f"Supplemental cases overlap the benchmark training partition: {overlap}")

    centroid = fit_centroid_model(train_rows)
    channel_evidence = build_channel_attribution(train_rows)
    deterministic = [
        majority_class_predict(train_rows, supplemental),
        intent_only_predict(supplemental),
        weighted_deterministic_predict(supplemental),
        baseline_a_predict(supplemental),
        baseline_b_predict(supplemental, centroid),
        baseline_c_predict(supplemental, centroid, channel_evidence),
        baseline_d_predict(supplemental, centroid),
    ]
    results_by_system: dict[str, list[BaselineResult]] = {result.name: [result] for result in deterministic}
    decision_records: list[dict[str, object]] = []
    temperatures: dict[str, float] = {}
    for seed in SEEDS:
        engine = RecommendationEngine(args.training_dataset, audited_benchmark=args.benchmark, seed=seed)
        temperatures[str(seed)] = engine.temperature
        for name, variant in SYSTEM_VARIANTS.items():
            results_by_system.setdefault(name, []).append(proposed_predict(engine, supplemental, name, variant))
        for row in supplemental:
            result = engine.recommend(row, engine.default_rules, row["Intent"], "Balanced", "full")
            decision_records.append({
                "Review_Case_ID": row["Review_Case_ID"], "Campaign_ID": row["Campaign_ID"], "Seed": seed,
                "Prediction": result.action, "Confidence": result.confidence,
                "Decision_Status": result.decision_status, "Coverage_Status": result.coverage_status,
                "Coverage_Reasons": "; ".join(result.coverage_reasons),
                "Preferred_Action": row["label"], "Preferred_Correct": int(result.action == row["label"]),
                "Admissible_Correct": int(result.action in row["admissible"]),
                "Unacceptable": int(result.action in row["unacceptable"]),
            })

    metrics = {name: mean_metrics(results, supplemental) for name, results in results_by_system.items()}
    intervals = {name: bootstrap_intervals(results, supplemental, args.bootstrap_samples) for name, results in results_by_system.items()}
    metric_names = list(next(iter(metrics.values())))
    write_csv(args.output_dir / "metrics.csv", [["System", *metric_names], *[[name, *[f"{values[metric]:.6f}" for metric in metric_names]] for name, values in metrics.items()]])

    seed_rows = [["System", "Seed", *metric_names]]
    for name, results in results_by_system.items():
        for index, result in enumerate(results):
            seed = "deterministic" if len(results) == 1 else SEEDS[index]
            values = set_metrics(result, supplemental)
            seed_rows.append([name, seed, *[f"{values[metric]:.6f}" for metric in metric_names]])
    write_csv(args.output_dir / "seed_metrics.csv", seed_rows)

    prediction_rows = [["Review_Case_ID", "Campaign_ID", "Intent", "Preferred_Action", "Acceptable_Actions", "Conditional_Actions", "Unacceptable_Actions", "System", "Seed", "Prediction", "Confidence", "Top_2", "Preferred_Correct", "Strict_Acceptable", "Admissible_Correct", "Unacceptable", "Latency_ms"]]
    for name, results in results_by_system.items():
        for index, result in enumerate(results):
            seed = "deterministic" if len(results) == 1 else SEEDS[index]
            for position, row in enumerate(supplemental):
                prediction = result.predictions[position]
                prediction_rows.append([
                    row["Review_Case_ID"], row["Campaign_ID"], row["Intent"], row["label"], "; ".join(row["acceptable"]), "; ".join(row["conditional"]), "; ".join(row["unacceptable"]),
                    name, seed, prediction, f"{result.confidences[position]:.6f}", " | ".join(result.top2_predictions[position]),
                    int(prediction == row["label"]), int(prediction in row["acceptable"]), int(prediction in row["admissible"]), int(prediction in row["unacceptable"]),
                    f"{result.case_latencies_ms[position]:.6f}",
                ])
    write_csv(args.output_dir / "predictions.csv", prediction_rows)

    write_csv(args.output_dir / "decision_statuses.csv", [list(decision_records[0]), *[[record[key] for key in decision_records[0]] for record in decision_records]])
    per_intent = [["System", "Intent", "Cases", *metric_names]]
    for name, results in results_by_system.items():
        for intent in ("Growth", "Retention", "Survival"):
            indices = [i for i, row in enumerate(supplemental) if row["Intent"] == intent]
            intent_rows = [supplemental[i] for i in indices]
            intent_results = [BaselineResult(result.name, [result.predictions[i] for i in indices], [result.confidences[i] for i in indices], [result.explanations[i] for i in indices], result.latency_ms, [result.top2_predictions[i] for i in indices], [result.case_latencies_ms[i] for i in indices]) for result in results]
            values = mean_metrics(intent_results, intent_rows)
            per_intent.append([name, intent, len(indices), *[f"{values[metric]:.6f}" for metric in metric_names]])
    write_csv(args.output_dir / "per_intent_metrics.csv", per_intent)

    full_seed42 = results_by_system["P: Full Proposed Method"][0]
    write_csv(args.output_dir / "reliability_seed42.csv", reliability_rows(full_seed42, supplemental))
    full_decisions = [record for record in decision_records if record["Seed"] == SEEDS[0]]
    status_counts = Counter(str(record["Decision_Status"]) for record in full_decisions)
    recommend = [record for record in full_decisions if record["Decision_Status"] == "RECOMMEND"]
    selective = {
        "seed": SEEDS[0],
        "status_counts": dict(status_counts),
        "automatic_recommend_coverage": len(recommend) / len(full_decisions),
        "automatic_recommend_admissible_accuracy": statistics.fmean(float(record["Admissible_Correct"]) for record in recommend) if recommend else None,
        "automatic_recommend_unacceptable_rate": statistics.fmean(float(record["Unacceptable"]) for record in recommend) if recommend else None,
        "out_of_coverage_cases": sum(record["Coverage_Status"] != "IN_SCOPE" for record in full_decisions),
    }
    (args.output_dir / "confidence_intervals.json").write_text(json.dumps(intervals, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "selective_policy_summary.json").write_text(json.dumps(selective, indent=2) + "\n", encoding="utf-8")

    timestamp = datetime.now().astimezone()
    metadata = {
        "run_id": f"R-SUP-50-{timestamp.strftime('%Y%m%dT%H%M%S%z')}",
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "evaluation_type": "post_confirmatory_supplemental_heldout_action_set_evaluation",
        "interpretation": "Same-source held-out robustness evidence; not external validation and not a replacement for the original 19-case confirmatory test.",
        "evaluation_timing": "Model outputs were generated only after independent reviews, adjudication and action-set freeze.",
        "source_commit": git_output("rev-parse", "HEAD"),
        "source_tags": git_output("tag", "--points-at", "HEAD").splitlines(),
        "source_tree_status": "dirty" if git_output(
            "status", "--porcelain", "--untracked-files=no",
        ) else "clean",
        "cases": len(supplemental), "seeds": list(SEEDS), "bootstrap_samples": args.bootstrap_samples,
        "case_file": str(args.cases), "case_file_sha256": sha256(args.cases),
        "action_set_file": str(args.action_sets), "action_set_file_sha256": sha256(args.action_sets),
        "benchmark_file": str(args.benchmark), "benchmark_file_sha256": sha256(args.benchmark),
        "training_dataset": str(args.training_dataset), "training_dataset_sha256": sha256(args.training_dataset),
        "train_overlap_cases": overlap, "temperatures": temperatures,
        "preferred_distribution": dict(Counter(row["label"] for row in supplemental)),
        "intent_distribution": dict(Counter(row["Intent"] for row in supplemental)),
        "primary_endpoint": "Admissible Set Accuracy (Acceptable or Conditional)",
        "secondary_endpoints": ["Preferred Macro F1", "Preferred Exact Accuracy", "Top-2 Preferred Hit", "Strict Acceptable Rate", "Unacceptable Recommendation Rate", "Top-2 Admissible Hit", "P95 Latency (ms)"],
        "software_environment": {"os": platform.platform(), "python": sys.version.split()[0]},
        "selective_policy_seed42": selective,
    }
    (args.output_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    summary = [
        "# Supplemental 50-Case Held-Out Evaluation",
        "",
        "This is same-source, post-confirmatory robustness evidence. The cases were not used for model fitting, calibration, threshold selection or action-set construction from model outputs.",
        "",
        "## Preferred-label comparison",
        "",
        "| System | Macro F1 | Exact accuracy | Top-2 preferred | Scenario fit | Conflict | ECE (preferred) | P95 latency (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, values in metrics.items():
        summary.append(f"| {name} | {values['Preferred Macro F1']:.4f} | {values['Preferred Exact Accuracy']:.2%} | {values['Top-2 Preferred Hit']:.2%} | {values['Scenario-Fit Rate']:.2%} | {values['Rule-Catalogue Conflict Rate']:.2%} | {values['ECE vs Preferred']:.4f} | {values['P95 Latency (ms)']:.3f} |")
    summary.extend([
        "",
        "## Action-set evaluation",
        "",
        "| System | Strict acceptable | Admissible set accuracy | Top-2 admissible | Unacceptable | ECE (admissible) |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for name, values in metrics.items():
        summary.append(f"| {name} | {values['Strict Acceptable Rate']:.2%} | {values['Admissible Set Accuracy']:.2%} | {values['Top-2 Admissible Hit']:.2%} | {values['Unacceptable Recommendation Rate']:.2%} | {values['ECE vs Admissible Set']:.4f} |")
    summary.extend(["", f"Seed-42 selective status counts: {dict(status_counts)}.", "", "Do not pool this cohort silently with the original 19-case confirmatory test; report the two protocols separately."])
    (args.output_dir / "SUPPLEMENTAL_EVALUATION_SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps({"metadata": metadata, "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
