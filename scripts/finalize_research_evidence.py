#!/usr/bin/env python3
"""Generate the final technical, integrity and faithfulness evidence package."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import torch

from baseline_evaluation import ACTION_ORDER, conflict_reasons
from scripts.run_confirmatory_evaluation import SEEDS, load_rows, split_rows
from system_components.neuro_symbolic_reasoning_layer.engine import (
    MIN_AUTO_CONFIDENCE,
    MIN_TOP_TWO_MARGIN,
    RecommendationEngine,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "final_evidence"
BENCHMARK = ROOT / "data" / "benchmark_audited.csv"
TRAINING_DATA = ROOT / "data" / "layers" / "02_processed_model_data.csv"
ACTION_SETS = ROOT / "outputs" / "supervision_evidence" / "action_set_review_approved_protocol.csv"
INTERVENTIONS = ROOT / "outputs" / "supervision_evidence" / "safeguard_intervention_audit.csv"
NUMERIC_FIELDS = (
    "Duration", "Impressions", "Clicks", "Leads", "Conversions", "Revenue",
    "Acquisition_Cost", "ROI", "Engagement_Score", "ctr", "conversion_rate",
    "lead_to_conversion", "cost_per_conversion",
)
BIN_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def write_csv(path: Path, rows: list[dict], headers: list[str] | None = None) -> None:
    headers = headers or (list(rows[0]) if rows else [])
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def source_tree_clean() -> bool:
    """Ignore generated evidence while checking whether source inputs are frozen."""
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return False
    status = result.stdout
    if not status:
        return True
    generated_prefixes = ("outputs/", "logs/", "results/", "refine-logs/")
    source_changes = []
    for line in status.splitlines():
        path = line[3:].replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not path.startswith(generated_prefixes):
            source_changes.append(path)
    return not source_changes


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def result_signature(result) -> tuple:
    return (
        result.action,
        round(result.confidence, 10),
        tuple((item["action"], round(float(item["score"]), 10)) for item in result.ranked_actions),
        tuple((item["code"], item["action"], item["triggered"]) for item in result.rule_results),
        tuple(sorted(result.explanation.items())),
    )


def explanation_faithfulness(engine: RecommendationEngine, rows: list[dict]) -> tuple[list[dict], dict]:
    audits = []
    for row in rows:
        result = engine.recommend(row, engine.default_rules, row["Intent"])
        driver = result.explanation.get("driver", "").casefold()
        top_feature = (
            str(result.attribution[0]["feature"]).replace("_", " ")
            if result.attribution else "campaign performance"
        )
        top_channel = str(result.channel_attribution[0]["channel"]) if result.channel_attribution else "reported channels"
        source_supported = (
            top_feature.casefold() in driver
            and top_channel.casefold() in driver
            and row["Intent"].casefold() in result.explanation.get("intent", "").casefold()
            and all(result.explanation.get(field, "").strip() for field in ("driver", "implication", "action", "caveat"))
        )

        selected_rules = [
            item for item in result.rule_results
            if item["action"] == result.action and item["triggered"]
        ]
        caveat = result.explanation.get("caveat", "")
        rule_consistent = all(item["detail"] in caveat for item in selected_rules[:2])
        if not selected_rules and caveat.startswith("Review required:"):
            rule_consistent = False

        changed = False
        perturbations = (
            ("ROI", -5.0 if float(row["ROI"]) >= 0 else 5.0),
            ("Engagement_Score", 0.0 if float(row["Engagement_Score"]) >= 5 else 100.0),
            ("Clicks", 0.0 if float(row["Clicks"]) >= 500 else 100000.0),
            ("Conversions", 0.0 if float(row["Conversions"]) >= 50 else 10000.0),
        )
        original_signature = result_signature(result)
        for field, value in perturbations:
            changed_case = dict(row)
            changed_case[field] = value
            perturbed = engine.recommend(changed_case, engine.default_rules, row["Intent"])
            if result_signature(perturbed) != original_signature:
                changed = True
                break

        metadata_case = dict(row)
        metadata_case["Campaign_ID"] = f"UNUSED-{row['Campaign_ID']}"
        metadata_case["Date"] = "01-01-2099"
        metadata_result = engine.recommend(metadata_case, engine.default_rules, row["Intent"])
        unused_invariant = result_signature(metadata_result) == original_signature

        audits.append({
            "Campaign_ID": row["Campaign_ID"],
            "Partition": "Test",
            "Recommended_Action": result.action,
            "Decision_Status": result.decision_status,
            "Top_Driver_Feature": top_feature,
            "Top_Channel_Evidence": top_channel,
            "Source_Fact_Support": "Pass" if source_supported else "Fail",
            "Triggered_Rule_Consistency": "Pass" if rule_consistent else "Fail",
            "Material_Perturbation_Response": "Pass" if changed else "Fail",
            "Unused_Metadata_Invariance": "Pass" if unused_invariant else "Fail",
            "Overall": "Pass" if all((source_supported, rule_consistent, changed, unused_invariant)) else "Fail",
        })
    checks = (
        "Source_Fact_Support", "Triggered_Rule_Consistency",
        "Material_Perturbation_Response", "Unused_Metadata_Invariance", "Overall",
    )
    summary = {
        "cases": len(audits),
        **{field: sum(row[field] == "Pass" for row in audits) for field in checks},
    }
    return audits, summary


def unconstrained_error_taxonomy(engine: RecommendationEngine, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    cases = []
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        result = engine.recommend(
            row, engine.default_rules, row["Intent"], ablation="without_rules",
        )
        reasons = conflict_reasons(row, result.action)
        categories = []
        if any(reason.startswith("intent:") for reason in reasons):
            categories.append("Intent conflict")
        if any(reason.startswith("performance:") for reason in reasons):
            categories.append("Performance conflict")
        if any(reason.startswith("evidence:") for reason in reasons):
            categories.append("Evidence-sufficiency conflict")
        if result.action != row["label"]:
            categories.append("Primary-reference disagreement")
            if result.confidence >= .50:
                categories.append("Confident disagreement")
        if not categories:
            continue
        for category in categories:
            counts[(category, result.action)] += 1
        cases.append({
            "Campaign_ID": row["Campaign_ID"],
            "Intent": row["Intent"],
            "Reference_Action": row["label"],
            "Unconstrained_Action": result.action,
            "Confidence": round(result.confidence, 6),
            "Unsafe": "Yes" if reasons else "No",
            "Categories": "; ".join(categories),
            "Conflict_Reasons": "; ".join(reasons),
            "Affected_Action": result.action,
        })
    summary = [
        {"Category": category, "Affected_Action": action, "Count": count}
        for (category, action), count in sorted(counts.items())
    ]
    return cases, summary


def benchmark_integrity(rows: list[dict]) -> tuple[list[dict], dict]:
    train, validation, test = split_rows(rows)
    partition = {
        row["Campaign_ID"]: name
        for name, items in (("Train", train), ("Validation", validation), ("Test", test))
        for row in items
    }
    ranges = {
        field: max(float(row[field]) for row in rows) - min(float(row[field]) for row in rows)
        for field in NUMERIC_FIELDS
    }
    pairs = []
    exact_pairs = 0
    cross_partition_pairs = 0
    for left_index, left in enumerate(rows):
        for right in rows[left_index + 1:]:
            same_template = all(
                str(left.get(field, "")).strip().casefold() == str(right.get(field, "")).strip().casefold()
                for field in ("Campaign_Type", "Target_Audience", "Channel_Used", "Intent")
            )
            if not same_template:
                continue
            deltas = [
                abs(float(left[field]) - float(right[field])) / (ranges[field] or 1.0)
                for field in NUMERIC_FIELDS
            ]
            distance = math.sqrt(statistics.fmean(delta * delta for delta in deltas))
            exact = all(delta == 0 for delta in deltas)
            if distance > .05 and not exact:
                continue
            cross = partition[left["Campaign_ID"]] != partition[right["Campaign_ID"]]
            exact_pairs += int(exact)
            cross_partition_pairs += int(cross)
            pairs.append({
                "Case_A": left["Campaign_ID"],
                "Partition_A": partition[left["Campaign_ID"]],
                "Case_B": right["Campaign_ID"],
                "Partition_B": partition[right["Campaign_ID"]],
                "Normalised_Distance": round(distance, 6),
                "Exact_Feature_Duplicate": "Yes" if exact else "No",
                "Cross_Partition": "Yes" if cross else "No",
                "Template_Fields": "Campaign_Type; Target_Audience; Channel_Used; Intent",
            })
    summary = {
        "records": len(rows),
        "unique_campaign_ids": len({row["Campaign_ID"] for row in rows}),
        "exact_feature_duplicate_pairs": exact_pairs,
        "near_duplicate_pairs_threshold_0_05": len(pairs),
        "cross_partition_near_duplicate_pairs": cross_partition_pairs,
        "partition_sizes": {"Train": len(train), "Validation": len(validation), "Test": len(test)},
        "partition_id_overlap": False,
        "near_duplicate_definition": (
            "Same campaign type, target audience, channel set and intent, with root-mean-square "
            "normalised numeric-feature distance <= 0.05."
        ),
    }
    return pairs, summary


def validate_action_sets(path: Path) -> tuple[list[dict], dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    expected = set(ACTION_ORDER)
    audit = []
    for row in rows:
        groups = {
            "Acceptable": {item.strip() for item in row["Acceptable_Action_Set"].split(";") if item.strip()},
            "Conditional": {item.strip() for item in row["Conditionally_Acceptable_Action_Set"].split(";") if item.strip()},
            "Unacceptable": {item.strip() for item in row["Unacceptable_Action_Set"].split(";") if item.strip()},
        }
        union = set().union(*groups.values())
        overlap = (
            groups["Acceptable"] & groups["Conditional"]
            or groups["Acceptable"] & groups["Unacceptable"]
            or groups["Conditional"] & groups["Unacceptable"]
        )
        valid = union == expected and not overlap and row["Current_Primary_Reference_Action"] in union
        audit.append({
            "Case_ID": row["Case_ID"],
            "Partition": row["Partition"],
            "Covers_Four_Actions": "Pass" if union == expected else "Fail",
            "Sets_Non_Overlapping": "Pass" if not overlap else "Fail",
            "Primary_Action_In_Partition": "Pass" if row["Current_Primary_Reference_Action"] in union else "Fail",
            "Overall": "Pass" if valid else "Fail",
        })
    return audit, {
        "records": len(audit),
        "valid_records": sum(row["Overall"] == "Pass" for row in audit),
        "invalid_records": sum(row["Overall"] != "Pass" for row in audit),
    }


def reliability_rows(engine: RecommendationEngine, rows: list[dict], partition: str, seed: int) -> tuple[list[dict], dict]:
    outputs = [engine.recommend(row, engine.default_rules, row["Intent"]) for row in rows]
    confidences = [result.confidence for result in outputs]
    correct = [int(result.action == row["label"]) for result, row in zip(outputs, rows)]
    table = []
    ece = 0.0
    for index, (lower, upper) in enumerate(zip(BIN_EDGES[:-1], BIN_EDGES[1:]), 1):
        indices = [
            item for item, confidence in enumerate(confidences)
            if lower <= confidence < upper or (index == 5 and confidence == 1.0)
        ]
        count = len(indices)
        hits = sum(correct[item] for item in indices)
        mean_confidence = statistics.fmean(confidences[item] for item in indices) if indices else None
        accuracy = hits / count if count else None
        gap = abs(mean_confidence - accuracy) if count else None
        contribution = count / len(rows) * gap if count else 0.0
        ece += contribution
        table.append({
            "Partition": partition,
            "Seed": seed,
            "Bin": index,
            "Interval": f"[{lower:.1f}, {upper:.1f}{']' if index == 5 else ')'}",
            "Eligible_Cases_n": count,
            "Correct_Cases_k": hits,
            "Mean_Confidence": "" if mean_confidence is None else round(mean_confidence, 6),
            "Observed_Accuracy": "" if accuracy is None else round(accuracy, 6),
            "Absolute_Gap": "" if gap is None else round(gap, 6),
            "ECE_Contribution": round(contribution, 6),
        })
    probabilities = [
        {item["action"]: float(item["score"]) for item in result.ranked_actions}
        for result in outputs
    ]
    nll = -statistics.fmean(math.log(max(values[row["label"]], 1e-12)) for values, row in zip(probabilities, rows))
    brier = statistics.fmean(
        sum((values[action] - int(row["label"] == action)) ** 2 for action in ACTION_ORDER)
        for values, row in zip(probabilities, rows)
    )
    summary = {
        "Partition": partition,
        "Seed": seed,
        "Cases": len(rows),
        "ECE": round(ece, 6),
        "NLL": round(nll, 6),
        "Brier_Score": round(brier, 6),
        "Increase_Support": sum(row["label"] == "Increase" for row in rows),
        "Qualification": (
            "Descriptive small-sample evidence; no Increase-class calibration claim."
            if not any(row["label"] == "Increase" for row in rows)
            else "Descriptive small-sample evidence; no population-level calibration claim."
        ),
    }
    return table, summary


def risk_coverage(engine: RecommendationEngine, rows: list[dict], partition: str) -> list[dict]:
    cases = []
    for row in rows:
        result = engine.recommend(row, engine.default_rules, row["Intent"])
        margin = result.ranked_actions[0]["score"] - result.ranked_actions[1]["score"]
        base_eligible = (
            result.action != "Investigate"
            and result.decision_status != "NO SAFE RECOMMENDATION"
            and not (result.action == "Increase" and row.get("Budget") in {None, ""})
            and margin >= MIN_TOP_TWO_MARGIN
            and not any(
                item["action"] == result.action and item["triggered"]
                for item in result.rule_results
            )
        )
        cases.append((row, result, margin, base_eligible))
    curve = []
    thresholds = sorted({round(value / 20, 2) for value in range(21)} | {MIN_AUTO_CONFIDENCE})
    for threshold in thresholds:
        accepted = [item for item in cases if item[3] and item[1].confidence >= threshold]
        curve.append({
            "Partition": partition,
            "Seed": engine.seed,
            "Confidence_Threshold": threshold,
            "Minimum_Top_Two_Margin": MIN_TOP_TWO_MARGIN,
            "Selected_Operating_Point": "Yes" if threshold == MIN_AUTO_CONFIDENCE else "No",
            "Accepted_Cases": len(accepted),
            "Coverage": round(len(accepted) / len(rows), 6),
            "Accepted_Accuracy": (
                "" if not accepted else round(sum(result.action == row["label"] for row, result, _, _ in accepted) / len(accepted), 6)
            ),
            "Accepted_Conflict_Rate": (
                "" if not accepted else round(sum(bool(conflict_reasons(row, result.action)) for row, result, _, _ in accepted) / len(accepted), 6)
            ),
        })
    return curve


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = load_rows(BENCHMARK)
    train_rows, validation_rows, test_rows = split_rows(rows)
    engine = RecommendationEngine(TRAINING_DATA, audited_benchmark=BENCHMARK, seed=42)

    faithfulness, faithfulness_summary = explanation_faithfulness(engine, test_rows)
    write_csv(OUTPUT / "explanation_faithfulness_case_audit.csv", faithfulness)
    (OUTPUT / "explanation_faithfulness_summary.json").write_text(
        json.dumps(faithfulness_summary, indent=2) + "\n", encoding="utf-8",
    )

    errors, error_summary = unconstrained_error_taxonomy(engine, test_rows)
    write_csv(OUTPUT / "unconstrained_error_cases.csv", errors)
    write_csv(OUTPUT / "unconstrained_error_summary.csv", error_summary)

    duplicate_pairs, integrity_summary = benchmark_integrity(rows)
    duplicate_headers = [
        "Case_A", "Partition_A", "Case_B", "Partition_B", "Normalised_Distance",
        "Exact_Feature_Duplicate", "Cross_Partition", "Template_Fields",
    ]
    write_csv(OUTPUT / "benchmark_near_duplicate_pairs.csv", duplicate_pairs, duplicate_headers)
    action_set_audit, action_set_summary = validate_action_sets(ACTION_SETS)
    write_csv(OUTPUT / "action_set_partition_validation.csv", action_set_audit)
    integrity_summary["action_set_validation"] = action_set_summary
    (OUTPUT / "benchmark_integrity_summary.json").write_text(
        json.dumps(integrity_summary, indent=2) + "\n", encoding="utf-8",
    )

    reliability_table, reliability_summary = [], []
    for seed in SEEDS:
        seeded = RecommendationEngine(TRAINING_DATA, audited_benchmark=BENCHMARK, seed=seed)
        for partition, partition_rows in (("Validation", validation_rows), ("Test", test_rows)):
            table, summary = reliability_rows(seeded, partition_rows, partition, seed)
            reliability_table.extend(table)
            reliability_summary.append(summary)
    write_csv(OUTPUT / "reliability_table.csv", reliability_table)
    write_csv(OUTPUT / "calibration_summary.csv", reliability_summary)
    write_csv(
        OUTPUT / "risk_coverage_curve.csv",
        risk_coverage(engine, validation_rows, "Validation") + risk_coverage(engine, test_rows, "Test"),
    )

    failures = []
    for row in test_rows:
        result = engine.recommend(row, engine.default_rules, row["Intent"])
        reasons = conflict_reasons(row, result.action)
        if result.action == row["label"] and result.decision_status == "RECOMMEND" and not reasons:
            continue
        failures.append({
            "Campaign_ID": row["Campaign_ID"],
            "Intent": row["Intent"],
            "Reference_Action": row["label"],
            "Recommended_Action": result.action,
            "Confidence": round(result.confidence, 6),
            "Decision_Status": result.decision_status,
            "Conflict_Reasons": "; ".join(reasons),
            "Failure_Type": (
                "Logical conflict" if reasons else
                "Reference disagreement" if result.action != row["label"] else
                "Selective review escalation"
            ),
        })
    write_csv(OUTPUT / "failure_cases.csv", failures)

    with INTERVENTIONS.open(newline="", encoding="utf-8-sig") as handle:
        intervention_rows = [
            row for row in csv.DictReader(handle)
            if row["Candidate_Safe_Intervention"] == "Yes"
        ]
    write_csv(OUTPUT / "safeguard_interventions.csv", intervention_rows)

    provenance_paths = [
        ROOT / "data" / "layers" / "01_raw_dataset_55555x16.csv",
        TRAINING_DATA,
        BENCHMARK,
        ROOT / "data" / "rule_catalogue_v1.json",
        ACTION_SETS,
    ]
    provenance = [
        {
            "Role": role,
            "Path": str(path.relative_to(ROOT)),
            "SHA256": sha256(path),
            "Bytes": path.stat().st_size,
        }
        for role, path in zip(
            ("Raw source", "Processed model data", "Audited benchmark", "Frozen rule catalogue", "Reviewed action sets"),
            provenance_paths,
        )
    ]
    write_csv(OUTPUT / "data_provenance_and_hashes.csv", provenance)

    rule_catalogue = json.loads((ROOT / "data" / "rule_catalogue_v1.json").read_text(encoding="utf-8"))
    write_csv(
        OUTPUT / "safeguard_classification.csv",
        [
            {
                "Code": rule["code"],
                "Name": rule["name"],
                "Constraint_Type": rule["constraint_type"],
                "Condition": rule["condition"],
                "Weight": rule["weight"],
                "Priority": rule["priority"],
                "Classification_Basis": rule["classification_basis"],
            }
            for rule in rule_catalogue["rules"]
        ],
    )

    environment = {
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "operating_system": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "packages": {
            name: package_version(name)
            for name in ("fastapi", "numpy", "pandas", "scikit-learn", "sqlalchemy", "pydantic")
        },
    }
    (OUTPUT / "environment.json").write_text(
        json.dumps(environment, indent=2) + "\n", encoding="utf-8",
    )

    limitations = """# Final evidence limitations

- The recommendation unit is one operational action: Increase, Maintain, Reduce or Investigate. Channel selection is not the primary output.
- Each case has exactly one declared primary intent: Survival, Retention or Growth. Mixed intent is outside the study scope and must be routed to human review.
- The 19-case validation partition contains no Increase reference cases. Calibration is therefore aggregate, profile-specific descriptive evidence and does not establish Increase-class or population-level calibration.
- The held-out test partition contains 19 cases. Coverage, correctness, conflict and faithfulness findings are small-sample technical evidence.
- The source benchmark does not provide complete business size, business maturity or prohibited-action fields. These are documented limitations and are not imputed or invented.
- Formal TAR UMT ethics approval is recorded; human-reliance results remain unavailable until genuine participant responses are collected under that approved scope.
"""
    (OUTPUT / "LIMITATIONS.md").write_text(limitations, encoding="utf-8")

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_commit": git_output("rev-parse", "HEAD"),
        "source_tags": git_output("tag", "--points-at", "HEAD").splitlines(),
        "source_tree_clean_at_generation": source_tree_clean(),
        "scope": {
            "recommendation_unit": list(ACTION_ORDER),
            "single_intent_only": ["Survival", "Retention", "Growth"],
            "mixed_intent": "out_of_scope_route_to_human_review",
        },
        "records": {"train": len(train_rows), "validation": len(validation_rows), "test": len(test_rows)},
        "faithfulness": faithfulness_summary,
        "unconstrained_error_cases": len(errors),
        "benchmark_integrity": integrity_summary,
        "calibration": {
            "bins": list(BIN_EDGES),
            "summaries": reliability_summary,
            "zero_increase_validation_limitation": True,
        },
        "selective_policy": {
            "confidence_threshold": MIN_AUTO_CONFIDENCE,
            "top_two_margin_threshold": MIN_TOP_TWO_MARGIN,
        },
        "set_based_safeguard_interventions": len(intervention_rows),
        "ethics_approval": {
            "authority": "TAR UMT Ethics Committee",
            "document": "Ethics Committee Checklist",
            "verified": True,
            "study_status": "approved_pending_participant_collection",
        },
        "environment_file": "environment.json",
        "limitations_file": "LIMITATIONS.md",
        "status": "technical_evidence_complete_human_study_approved_pending_participants",
    }
    (OUTPUT / "FINAL_EVIDENCE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
