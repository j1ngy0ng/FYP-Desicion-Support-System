#!/usr/bin/env python3
"""Run non-confirmatory baseline and proposed-system development evaluation."""

from __future__ import annotations

import argparse
import csv
import json
import time
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
    fit_centroid_model,
    split_channels,
)
from system_components.data_management_layer.data_preprocessing import prepare_frame
from system_components.neuro_symbolic_reasoning_layer.candidate_action_generation import (
    ACTIONS,
    rank_actions,
)
from system_components.neuro_symbolic_reasoning_layer.engine import RecommendationEngine


SYNTHETIC_PROVENANCE = (
    "Synthetic rule-based development annotation; not independent human review"
)
HUMAN_PROVIDED_PROVENANCE = (
    "User-provided as human annotation; reviewer independence and adjudication not documented"
)
VARIANTS = {
    "Proposed System - Full Framework": "full",
    "Branch Ablation - CampaignNet Only": "campaignnet_only",
    "Branch Ablation - ActionNet Only": "actionnet_only",
    "Branch Ablation - Fused CampaignNet-ActionNet": "fused_evidence",
    "Proposed Ablation - Without Intent": "without_intent",
    "Proposed Ablation - Without Rules": "without_rules",
    "Proposed Ablation - Without Calibration": "without_calibration",
    "B4: Integrated Learned Backbone": "backbone",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run explicitly non-confirmatory evaluation on development annotations."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/Dataset_human_provided_development.csv"),
    )
    parser.add_argument(
        "--training-dataset",
        type=Path,
        default=Path("data/raw/nykaa_campaign_data.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/human_provided_development"),
    )
    parser.add_argument(
        "--annotation-kind",
        choices=("human-provided", "synthetic"),
        default="human-provided",
    )
    parser.add_argument("--ece-bins", type=int, default=10)
    return parser.parse_args()


def load_annotated_rows(path: Path, annotation_kind: str) -> list[dict]:
    frame = prepare_frame(path)
    required = {
        "Campaign_ID",
        "Reviewer_Intent",
        "Reviewer_Action",
        "Reviewer_Notes",
        "Annotation_Source",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError("Development dataset is missing: " + ", ".join(missing))
    expected_provenance = (
        SYNTHETIC_PROVENANCE
        if annotation_kind == "synthetic"
        else HUMAN_PROVIDED_PROVENANCE
    )
    if not frame["Annotation_Source"].eq(expected_provenance).all():
        raise ValueError("Every row must carry the expected annotation provenance marker.")
    if annotation_kind == "human-provided":
        if "Annotation_Status" not in frame:
            raise ValueError("Human-provided development data requires Annotation_Status.")
        if not frame["Annotation_Status"].eq("DevelopmentOnly").all():
            raise ValueError("Human-provided rows must remain DevelopmentOnly until audited.")
    if frame["Campaign_ID"].duplicated().any():
        raise ValueError("Campaign_ID must be unique.")

    rows: list[dict] = []
    for item in frame.to_dict("records"):
        action = canonical_action(str(item["Reviewer_Action"]))
        intent = str(item["Reviewer_Intent"]).strip().title()
        if action not in {"Increase", "Maintain", "Reduce", "Investigate"}:
            raise ValueError(f"Unsupported reviewer action: {action}")
        if intent not in {"Survival", "Retention", "Growth"}:
            raise ValueError(f"Unsupported reviewer intent: {intent}")
        item["label"] = action
        item["Reference_Action"] = action
        item["Intent"] = intent
        item["channels"] = split_channels(str(item.get("Channel_Used", "")))
        rows.append(item)
    return rows


def proposed_predict(
    engine: RecommendationEngine,
    rows: Sequence[dict],
    name: str,
    variant: str,
) -> BaselineResult:
    predictions: list[str] = []
    confidences: list[float] = []
    explanations: list[str] = []
    started = time.perf_counter()
    with torch.no_grad():
        for row in rows:
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
            action = canonical_action(str(ranked[0]["action"]))
            predictions.append(action)
            confidences.append(float(ranked[0]["score"]))
            triggered = sum(1 for result in rule_results if result["triggered"])
            explanations.append(
                "Intent-aware recommendation with predictive strength, training-derived channel evidence, "
                f"{triggered} triggered weighted rules, confidence evidence, and "
                f"calibration status {engine.calibration_status}; "
                f"{len(channels)} channel signals evaluated."
            )
    latency = (time.perf_counter() - started) * 1000 / max(1, len(rows))
    return BaselineResult(name, predictions, confidences, explanations, latency)


def save_metrics(path: Path, metrics: dict[str, dict[str, float]]) -> None:
    names = list(next(iter(metrics.values())))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["System", *names])
        for system, values in metrics.items():
            writer.writerow([system, *[f"{values[name]:.6f}" for name in names]])


def save_predictions(
    path: Path,
    rows: Sequence[dict],
    systems: Sequence[BaselineResult],
) -> None:
    headers = ["Campaign_ID", "Development_Intent", "Development_Reference_Action"]
    for index, system in enumerate(systems, 1):
        headers.extend(
            [
                f"System_{index}_Name",
                f"System_{index}_Prediction",
                f"System_{index}_Confidence",
                f"System_{index}_Conflict",
            ]
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(headers)
        for row_index, row in enumerate(rows):
            record = [row["Campaign_ID"], row["Intent"], row["label"]]
            for system in systems:
                prediction = system.predictions[row_index]
                record.extend(
                    [
                        system.name,
                        prediction,
                        f"{system.confidences[row_index]:.6f}",
                        int(bool(conflict_reasons(row, prediction))),
                    ]
                )
            writer.writerow(record)


def save_markdown(
    path: Path,
    metrics: dict[str, dict[str, float]],
    test_rows: int,
    calibration_status: str,
    annotation_kind: str,
) -> None:
    names = list(next(iter(metrics.values())))
    lines = [
        "# Human-Provided Development Evaluation"
        if annotation_kind == "human-provided"
        else "# Synthetic Development Evaluation",
        "",
        (
            "> **Non-confirmatory result:** the annotations were supplied as human-labelled, "
            "but reviewer independence, adjudication and audit status are not documented. "
            "Do not report these values as independently human-validated performance."
            if annotation_kind == "human-provided"
            else "> **Non-confirmatory result:** reference intents and actions are deterministic "
            "synthetic development annotations, not independent human labels. Do not report "
            "these values as human-validated model performance."
        ),
        "",
        f"- Chronological holdout cases: {test_rows:,}",
        "- Training partition: earliest 70%",
        "- Validation partition: next 15% (not scored here)",
        "- Test partition: latest 15%",
        f"- Proposed-system calibration status: `{calibration_status}`",
        "",
        "|" + "System|" + "|".join(names) + "|",
        "|" + "---|" + "|".join(["---"] * len(names)) + "|",
    ]
    for system, values in metrics.items():
        lines.append(
            "|" + "|".join([system, *[f"{values[name]:.4f}" for name in names]]) + "|"
        )
    lines.extend(
        [
            "",
            "Proxy measures are deterministic technical indicators and are not participant-study results.",
            "Because calibration remains locked pending human annotations, the full framework and "
            "without-calibration ablation are expected to use the same temperature.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    rows = load_annotated_rows(args.dataset, args.annotation_kind)
    train_end = max(1, int(len(rows) * 0.70))
    validation_end = max(train_end + 1, int(len(rows) * 0.85))
    train_rows = rows[:train_end]
    test_rows = rows[validation_end:]
    labels = [row["label"] for row in test_rows]

    centroid = fit_centroid_model(train_rows)
    channel_attribution = build_channel_attribution(train_rows)
    systems = [
        baseline_a_predict(test_rows),
        baseline_b_predict(test_rows, centroid),
        baseline_c_predict(test_rows, centroid, channel_attribution),
        baseline_d_predict(test_rows, centroid),
    ]

    engine = RecommendationEngine(
        args.training_dataset,
        args.dataset if args.annotation_kind == "human-provided" else None,
    )
    systems.extend(
        proposed_predict(engine, test_rows, name, variant)
        for name, variant in VARIANTS.items()
    )
    metrics = {
        system.name: evaluate_baseline(system, test_rows, labels, args.ece_bins)
        for system in systems
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_metrics(args.output_dir / "metrics.csv", metrics)
    save_predictions(args.output_dir / "predictions.csv", test_rows, systems)
    save_markdown(
        args.output_dir / "comparison_table.md",
        metrics,
        len(test_rows),
        engine.calibration_status,
        args.annotation_kind,
    )
    annotation_source = (
        HUMAN_PROVIDED_PROVENANCE
        if args.annotation_kind == "human-provided"
        else SYNTHETIC_PROVENANCE
    )
    metadata = {
        "evaluation_type": f"{args.annotation_kind.replace('-', '_')}_development_non_confirmatory",
        "dataset": str(args.dataset),
        "training_dataset": str(args.training_dataset),
        "records": len(rows),
        "training_records": len(train_rows),
        "validation_records": validation_end - train_end,
        "test_records": len(test_rows),
        "annotation_source": annotation_source,
        "calibration_status": engine.calibration_status,
        "confirmatory_use_allowed": False,
    }
    (args.output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Saved development evaluation to: {args.output_dir.resolve()}")
    print(json.dumps(metadata, indent=2))
    for system, values in metrics.items():
        print(
            f"{system}: accuracy={values['Recommendation Accuracy']:.4f}, "
            f"scenario_fit={values['Scenario-Fit Rate']:.4f}, "
            f"conflict={values['Logical Conflict Rate']:.4f}, "
            f"ece={values['Expected Calibration Error (ECE)']:.4f}"
        )


if __name__ == "__main__":
    main()
