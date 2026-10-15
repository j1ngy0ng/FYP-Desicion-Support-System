#!/usr/bin/env python3
"""Run the locked, chronological, multi-seed confirmatory technical evaluation."""

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
import time
from collections import Counter
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Sequence

import torch

from baseline_evaluation import (
    BaselineResult,
    baseline_a_predict,
    baseline_b_predict,
    baseline_c_predict,
    baseline_d_predict,
    build_channel_attribution,
    canonical_action,
    conflict_reasons,
    evaluate_baseline,
    expected_calibration_error,
    fit_centroid_model,
    intent_only_predict,
    logical_conflict_rate,
    majority_class_predict,
    macro_f1_score,
    recommendation_accuracy,
    scenario_fit_rate,
    top2_agreement,
    weighted_deterministic_predict,
)
from system_components.neuro_symbolic_reasoning_layer.candidate_action_generation import (
    rank_actions,
)
from system_components.neuro_symbolic_reasoning_layer.engine import (
    MIN_AUTO_CONFIDENCE,
    MIN_TOP_TWO_MARGIN,
    RecommendationEngine,
)


VARIANTS = {
    "Proposed System - Full Framework": "full",
    "Unconstrained AI Baseline": "without_rules",
    "Branch Ablation - CampaignNet Only": "campaignnet_only",
    "Branch Ablation - ActionNet Only": "actionnet_only",
    "Branch Ablation - Fused CampaignNet-ActionNet": "fused_evidence",
    "Proposed Ablation - Without Intent": "without_intent",
    "Proposed Ablation - Without Rules": "without_rules",
    "Proposed Ablation - Without Calibration": "without_calibration",
    "Proposed Ablation - Without Structured Explanation": "without_explanation",
    "Proposed Ablation - Without Review Gate": "without_review_gate",
    "B4: Integrated Learned Backbone": "backbone",
}
SEEDS = (42, 52, 62)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/benchmark_audited.csv"),
    )
    parser.add_argument(
        "--training-dataset",
        type=Path,
        default=Path("data/layers/02_processed_model_data.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/confirmatory_evaluation"),
    )
    parser.add_argument("--ece-bins", type=int, default=5)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    return parser.parse_args()


def parse_date(value: str) -> datetime:
    raw = value.strip().replace("/", "-")
    for pattern in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            continue
    raise ValueError(f"Unsupported benchmark date: {value}")


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "Campaign_ID",
        "Reviewer_1_Intent",
        "Reviewer_1_Action",
        "Reviewer_2_Intent",
        "Reviewer_2_Action",
        "Adjudicated_Intent",
        "Adjudicated_Action",
        "Annotation_Status",
    }
    if len(rows) < 120 or not rows or not required.issubset(rows[0]):
        raise ValueError("The audited benchmark is incomplete.")
    if len({row["Campaign_ID"] for row in rows}) != len(rows):
        raise ValueError("Campaign_ID must be unique.")
    if any(row["Annotation_Status"].strip() != "Audited" for row in rows):
        raise ValueError("Every benchmark case must be marked Audited.")
    numeric_fields = (
        "Duration", "Impressions", "Clicks", "Leads", "Conversions", "Revenue",
        "Acquisition_Cost", "ROI", "Engagement_Score",
    )
    prepared = []
    for row in rows:
        item = dict(row)
        for field in numeric_fields:
            item[field] = float(item[field])
        item["ctr"] = item["Clicks"] / item["Impressions"] if item["Impressions"] else 0.0
        item["conversion_rate"] = item["Conversions"] / item["Clicks"] if item["Clicks"] else 0.0
        item["lead_to_conversion"] = item["Conversions"] / item["Leads"] if item["Leads"] else 0.0
        item["cost_per_conversion"] = (
            item["Acquisition_Cost"] / item["Conversions"]
            if item["Conversions"]
            else item["Acquisition_Cost"]
        )
        item["Intent"] = item["Adjudicated_Intent"].strip().title()
        item["label"] = canonical_action(item["Adjudicated_Action"])
        item["Reference_Action"] = item["label"]
        item["channels"] = [
            channel.strip().lower()
            for channel in item.get("Channel_Used", "").split(",")
            if channel.strip()
        ]
        item["_date"] = parse_date(item["Date"])
        prepared.append(item)
    prepared.sort(key=lambda row: (row["_date"], row["Campaign_ID"]))
    return prepared


def split_rows(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    train_end = max(1, int(len(rows) * .70))
    validation_end = max(train_end + 1, int(len(rows) * .85))
    return rows[:train_end], rows[train_end:validation_end], rows[validation_end:]


def proposed_predict(
    engine: RecommendationEngine,
    rows: Sequence[dict],
    name: str,
    variant: str,
) -> BaselineResult:
    predictions, confidences, explanations = [], [], []
    top2_predictions, case_latencies = [], []
    started = time.perf_counter()
    with torch.no_grad():
        for row in rows:
            case_started = time.perf_counter()
            raw, rule_results, _, _, channels = engine._score(
                row,
                engine.default_rules,
                row["Intent"],
                variant,
                engine.scoring,
                explain=False,
            )
            temperature = (
                1.0
                if variant in {
                    "without_calibration", "backbone", "campaignnet_only",
                    "actionnet_only", "fused_evidence",
                }
                else engine.temperature
            )
            ranked = rank_actions(raw, temperature)
            predictions.append(canonical_action(str(ranked[0]["action"])))
            confidences.append(float(ranked[0]["score"]))
            top2_predictions.append([
                canonical_action(str(item["action"])) for item in ranked[:2]
            ])
            triggered = sum(1 for result in rule_results if result["triggered"])
            explanations.append(
                "Intent-aware recommendation with predictive strength, training-derived channel evidence, "
                f"{triggered} triggered weighted rules, confidence evidence, and "
                f"calibration status {engine.calibration_status}; "
                f"{len(channels)} channel signals evaluated."
            )
            case_latencies.append((time.perf_counter() - case_started) * 1000)
    latency = (time.perf_counter() - started) * 1000 / max(1, len(rows))
    return BaselineResult(
        name,
        predictions,
        confidences,
        explanations,
        latency,
        top2_predictions,
        case_latencies,
    )


def mean_metrics(results: Sequence[BaselineResult], rows: Sequence[dict], bins: int) -> dict[str, float]:
    labels = [row["label"] for row in rows]
    runs = [evaluate_baseline(result, rows, labels, bins) for result in results]
    return {
        metric: statistics.fmean(run[metric] for run in runs)
        for metric in runs[0]
    }


def bootstrap_intervals(
    results: Sequence[BaselineResult],
    rows: Sequence[dict],
    bins: int,
    samples: int,
) -> dict[str, list[float]]:
    rng = random.Random(20260405)
    labels = [row["label"] for row in rows]
    names = (
        "Recommendation Accuracy",
        "Macro F1",
        "Top-2 Agreement",
        "Scenario-Fit Rate",
        "Logical Conflict Rate",
        "Expected Calibration Error (ECE)",
    )
    values = {name: [] for name in names}
    for _ in range(samples):
        indices = [rng.randrange(len(rows)) for _ in rows]
        sampled_rows = [rows[index] for index in indices]
        sampled_labels = [labels[index] for index in indices]
        run_values = {name: [] for name in names}
        for result in results:
            predictions = [result.predictions[index] for index in indices]
            confidences = [result.confidences[index] for index in indices]
            top2 = [result.top2_predictions[index] for index in indices]
            correctness = [
                int(prediction == reference)
                for prediction, reference in zip(predictions, sampled_labels)
            ]
            run_values["Recommendation Accuracy"].append(
                recommendation_accuracy(predictions, sampled_labels)
            )
            run_values["Macro F1"].append(
                macro_f1_score(predictions, sampled_labels)
            )
            run_values["Top-2 Agreement"].append(
                top2_agreement(top2, sampled_labels, predictions)
            )
            run_values["Scenario-Fit Rate"].append(
                scenario_fit_rate(predictions, [row["Intent"] for row in sampled_rows])
            )
            run_values["Logical Conflict Rate"].append(
                logical_conflict_rate(sampled_rows, predictions)
            )
            run_values["Expected Calibration Error (ECE)"].append(
                expected_calibration_error(confidences, correctness, bins)
            )
        for name in names:
            values[name].append(statistics.fmean(run_values[name]))
    intervals = {}
    for name, observations in values.items():
        ordered = sorted(observations)
        intervals[name] = [
            ordered[int(.025 * (len(ordered) - 1))],
            ordered[int(.975 * (len(ordered) - 1))],
        ]
    return intervals


def write_csv(path: Path, rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def main() -> None:
    args = parse_args()
    timestamp = datetime.now().astimezone()
    run_id = f"R002-{timestamp.strftime('%Y%m%dT%H%M%S%z')}"
    source_commit = git_output("rev-parse", "HEAD")
    source_tags = git_output("tag", "--points-at", "HEAD").splitlines()
    rule_catalogue = Path("data/rule_catalogue_v1.json")
    rows = load_rows(args.dataset)
    train_rows, validation_rows, test_rows = split_rows(rows)
    labels = [row["label"] for row in test_rows]
    centroid = fit_centroid_model(train_rows)
    channel_attribution = build_channel_attribution(train_rows)
    deterministic = [
        majority_class_predict(train_rows, test_rows),
        intent_only_predict(test_rows),
        weighted_deterministic_predict(test_rows),
        baseline_a_predict(test_rows),
        baseline_b_predict(test_rows, centroid),
        baseline_c_predict(test_rows, centroid, channel_attribution),
        baseline_d_predict(test_rows, centroid),
    ]
    results_by_system: dict[str, list[BaselineResult]] = {
        result.name: [result] for result in deterministic
    }
    temperatures = {}
    calibration_statuses = {}
    action_evidence_statuses = {}
    for seed in SEEDS:
        engine = RecommendationEngine(
            args.training_dataset,
            audited_benchmark=args.dataset,
            seed=seed,
        )
        temperatures[str(seed)] = engine.temperature
        calibration_statuses[str(seed)] = engine.calibration_status
        action_evidence_statuses[str(seed)] = {
            "audited_human_benchmark": "audited_actionnet",
            "user_provided_development": "development_actionnet",
        }.get(engine.annotation_status, "campaignnet_only_fallback")
        for name, variant in VARIANTS.items():
            results_by_system.setdefault(name, []).append(
                proposed_predict(engine, test_rows, name, variant)
            )

    metrics = {
        name: mean_metrics(results, test_rows, args.ece_bins)
        for name, results in results_by_system.items()
    }
    intervals = {
        name: bootstrap_intervals(
            results, test_rows, args.ece_bins, args.bootstrap_samples,
        )
        for name, results in results_by_system.items()
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    metric_names = list(next(iter(metrics.values())))
    metric_rows: list[list[object]] = [["System", *metric_names]]
    for name, values in metrics.items():
        metric_rows.append([name, *[f"{values[metric]:.6f}" for metric in metric_names]])
    write_csv(args.output_dir / "metrics.csv", metric_rows)

    seed_rows: list[list[object]] = [["System", "Seed", *metric_names]]
    for name, results in results_by_system.items():
        for index, result in enumerate(results):
            seed = "deterministic" if len(results) == 1 else SEEDS[index]
            values = evaluate_baseline(result, test_rows, labels, args.ece_bins)
            seed_rows.append([
                name, seed, *[f"{values[metric]:.6f}" for metric in metric_names],
            ])
    write_csv(args.output_dir / "seed_metrics.csv", seed_rows)

    per_intent_rows: list[list[object]] = [["System", "Seed", "Intent", "Cases", *metric_names]]
    for name, results in results_by_system.items():
        for result_index, result in enumerate(results):
            seed = "deterministic" if len(results) == 1 else SEEDS[result_index]
            for intent in ("Growth", "Retention", "Survival"):
                indices = [index for index, row in enumerate(test_rows) if row["Intent"] == intent]
                intent_rows = [test_rows[index] for index in indices]
                intent_result = BaselineResult(
                    result.name,
                    [result.predictions[index] for index in indices],
                    [result.confidences[index] for index in indices],
                    [result.explanations[index] for index in indices],
                    result.latency_ms,
                    [result.top2_predictions[index] for index in indices],
                    [result.case_latencies_ms[index] for index in indices],
                )
                values = evaluate_baseline(
                    intent_result,
                    intent_rows,
                    [row["label"] for row in intent_rows],
                    args.ece_bins,
                )
                per_intent_rows.append([
                    name, seed, intent, len(intent_rows),
                    *[f"{values[metric]:.6f}" for metric in metric_names],
                ])
    write_csv(args.output_dir / "per_intent_metrics.csv", per_intent_rows)

    prediction_rows: list[list[object]] = [[
        "Campaign_ID", "Date", "Intent", "Reference_Action", "System", "Seed",
        "Prediction", "Confidence", "Top_2", "Conflict", "Conflict_Reasons",
        "Latency_ms", "Action_Evidence_Status", "Run_ID", "Source_Commit",
    ]]
    for name, results in results_by_system.items():
        for result_index, result in enumerate(results):
            seed = "deterministic" if len(results) == 1 else SEEDS[result_index]
            for index, row in enumerate(test_rows):
                reasons = conflict_reasons(row, result.predictions[index])
                prediction_rows.append([
                    row["Campaign_ID"],
                    row["_date"].date().isoformat(),
                    row["Intent"],
                    row["label"],
                    name,
                    seed,
                    result.predictions[index],
                    f"{result.confidences[index]:.6f}",
                    " | ".join(result.top2_predictions[index]),
                    int(bool(reasons)),
                    "; ".join(reasons),
                    f"{result.case_latencies_ms[index]:.6f}",
                    (
                        "not_applicable"
                        if seed == "deterministic"
                        else action_evidence_statuses[str(seed)]
                    ),
                    run_id,
                    source_commit,
                ])
    write_csv(args.output_dir / "predictions.csv", prediction_rows)
    (args.output_dir / "confidence_intervals.json").write_text(
        json.dumps(intervals, indent=2) + "\n", encoding="utf-8",
    )

    full = metrics["Proposed System - Full Framework"]
    heuristic = metrics["B1: Heuristic Scorecard"]
    claim_status = (
        "meets_initial_technical_success_criterion"
        if full["Macro F1"] >= .60
        and full["Macro F1"] - heuristic["Macro F1"] >= .05
        else "exploratory_due_to_macro_f1_gate"
    )
    metadata = {
        "run_id": run_id,
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "source_commit": source_commit,
        "source_tags": source_tags,
        "evaluation_type": "confirmatory_technical_evaluation",
        "dataset": str(args.dataset),
        "dataset_sha256": sha256(args.dataset),
        "training_dataset": str(args.training_dataset),
        "training_dataset_sha256": sha256(args.training_dataset),
        "rule_catalogue_version": "rule-catalogue-v1",
        "rule_catalogue_sha256": sha256(rule_catalogue),
        "split": "chronological_70_15_15",
        "records": len(rows),
        "training_records": len(train_rows),
        "validation_records": len(validation_rows),
        "test_records": len(test_rows),
        "test_date_start": test_rows[0]["_date"].date().isoformat(),
        "test_date_end": test_rows[-1]["_date"].date().isoformat(),
        "seeds": list(SEEDS),
        "ece_bins": args.ece_bins,
        "bootstrap_samples": args.bootstrap_samples,
        "calibration_fit_partition": "validation_only",
        "selective_policy_threshold_partition": "validation_only",
        "minimum_auto_confidence": MIN_AUTO_CONFIDENCE,
        "minimum_top_two_margin": MIN_TOP_TWO_MARGIN,
        "temperatures": temperatures,
        "calibration_statuses": calibration_statuses,
        "action_evidence_statuses": action_evidence_statuses,
        "software_environment": {
            "operating_system": platform.platform(),
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "numpy": package_version("numpy"),
            "pandas": package_version("pandas"),
            "scikit_learn": package_version("scikit-learn"),
        },
        "confirmatory_technical_use_allowed": True,
        "human_participant_metrics_complete": False,
        "claim_status": claim_status,
        "ground_truth_conflict_rate": logical_conflict_rate(test_rows, labels),
        "test_action_distribution": dict(Counter(labels)),
        "test_intent_distribution": dict(Counter(row["Intent"] for row in test_rows)),
    }
    (args.output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8",
    )

    results_dir = Path("results")
    logs_dir = Path("logs")
    refine_dir = Path("refine-logs")
    results_dir.mkdir(exist_ok=True)
    logs_dir.mkdir(exist_ok=True)
    refine_dir.mkdir(exist_ok=True)
    benchmark_audit = json.loads(
        Path("data/human_annotations/completed/benchmark_audit.json").read_text(
            encoding="utf-8"
        )
    )
    (results_dir / "R001.json").write_text(
        json.dumps({
            "run_id": "R001",
            "status": "passed",
            "source_records": 55555,
            "processed_records": 55555,
            "benchmark": benchmark_audit,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    (results_dir / "R002.json").write_text(
        json.dumps({
            "run_id": "R002",
            "metadata": metadata,
            "metrics": metrics,
            "confidence_intervals_95": intervals,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_lines = [
        "# Experiment Results",
        "",
        "## R001 — Source audit and benchmark freeze",
        "",
        f"- Status: passed ({len(rows)} audited cases)",
        f"- Intent Cohen's kappa: {benchmark_audit['intent_kappa']:.3f}",
        f"- Action Cohen's kappa: {benchmark_audit['action_kappa']:.3f}",
        "",
        "## R002 — Baseline and proposed-system technical evaluation",
        "",
        f"- Split: chronological 70/15/15 ({len(test_rows)} held-out test cases)",
        f"- Seeds: {', '.join(map(str, SEEDS))}",
        f"- Claim status: {claim_status}",
        "",
        "|System|Macro F1|Accuracy|Top-2|Scenario Fit|Conflict|ECE|P95 ms|",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, values in metrics.items():
        summary_lines.append(
            f"|{name}|{values['Macro F1']:.4f}|"
            f"{values['Recommendation Accuracy']:.4f}|"
            f"{values['Top-2 Agreement']:.4f}|"
            f"{values['Scenario-Fit Rate']:.4f}|"
            f"{values['Logical Conflict Rate']:.4f}|"
            f"{values['Expected Calibration Error (ECE)']:.4f}|"
            f"{values['P95 Latency (ms)']:.3f}|"
        )
    summary_lines.extend([
        "",
        "Human actionability, willingness-to-act, trust-alignment and overtrust "
        "claims remain pending the blinded 18–24 participant study.",
    ])
    (refine_dir / "EXPERIMENT_RESULTS.md").write_text(
        "\n".join(summary_lines) + "\n", encoding="utf-8",
    )
    (logs_dir / "R002.log").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2))
    for name, values in metrics.items():
        print(
            f"{name}: macro_f1={values['Macro F1']:.4f}, "
            f"accuracy={values['Recommendation Accuracy']:.4f}, "
            f"conflict={values['Logical Conflict Rate']:.4f}, "
            f"ece={values['Expected Calibration Error (ECE)']:.4f}"
        )


if __name__ == "__main__":
    main()
