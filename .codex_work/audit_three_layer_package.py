from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np


BASE = Path(
    r"C:\Users\user\Downloads\nykaa_three_layer_dataset(1)\nykaa_data_layers"
)
RAW = BASE / "01_raw_dataset_55555x16.csv"
PROCESSED = BASE / "02_processed_model_data.csv"
GOLD = BASE / "03_gold_benchmark_125.csv"
REVIEW = BASE / "03_gold_benchmark_review.xlsx"
RULES = BASE / "BUSINESS_RULES_AND_DATA_DICTIONARY.txt"
OUTPUT = Path(".codex_work/three_layer_audit/audit.json")


def load(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_divide(a: float, b: float) -> float:
    return a / b if b else 0.0


def max_error(rows: list[dict[str, str]], field: str, calculation) -> float:
    return max(abs(float(row[field]) - calculation(row)) for row in rows)


def cohen_kappa(left: list[str], right: list[str]) -> float:
    labels = sorted(set(left) | set(right))
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        (left_counts[label] / len(left)) * (right_counts[label] / len(right))
        for label in labels
    )
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


raw_fields, raw_rows = load(RAW)
processed_fields, processed_rows = load(PROCESSED)
gold_fields, gold_rows = load(GOLD)
raw_by_id = {row["Campaign_ID"]: row for row in raw_rows}

processed_source_match = (
    len(processed_rows) == len(raw_rows)
    and [row["Campaign_ID"] for row in processed_rows]
    == [row["Campaign_ID"] for row in raw_rows]
    and all(
        all(processed[field] == raw[field] for field in raw_fields)
        for raw, processed in zip(raw_rows, processed_rows)
    )
)

formula_errors = {
    "CTR": max_error(
        processed_rows,
        "CTR",
        lambda r: safe_divide(float(r["Clicks"]), float(r["Impressions"])),
    ),
    "Click_to_Lead_Rate": max_error(
        processed_rows,
        "Click_to_Lead_Rate",
        lambda r: safe_divide(float(r["Leads"]), float(r["Clicks"])),
    ),
    "Lead_to_Conversion_Rate": max_error(
        processed_rows,
        "Lead_to_Conversion_Rate",
        lambda r: safe_divide(float(r["Conversions"]), float(r["Leads"])),
    ),
    "Overall_Conversion_Rate": max_error(
        processed_rows,
        "Overall_Conversion_Rate",
        lambda r: safe_divide(float(r["Conversions"]), float(r["Impressions"])),
    ),
    "Revenue_per_Click": max_error(
        processed_rows,
        "Revenue_per_Click",
        lambda r: round(safe_divide(float(r["Revenue"]), float(r["Clicks"])), 2),
    ),
    "Revenue_per_Conversion": max_error(
        processed_rows,
        "Revenue_per_Conversion",
        lambda r: round(
            safe_divide(float(r["Revenue"]), float(r["Conversions"])), 2
        ),
    ),
    "Estimated_Total_Acquisition_Cost": max_error(
        processed_rows,
        "Estimated_Total_Acquisition_Cost",
        lambda r: round(float(r["Acquisition_Cost"]) * float(r["Conversions"]), 2),
    ),
    "ROAS_Proxy": max_error(
        processed_rows,
        "ROAS_Proxy",
        lambda r: round(
            safe_divide(
                float(r["Revenue"]),
                float(r["Acquisition_Cost"]) * float(r["Conversions"]),
            ),
            4,
        ),
    ),
    "Calculated_ROI_Proxy": max_error(
        processed_rows,
        "Calculated_ROI_Proxy",
        lambda r: round(
            safe_divide(
                float(r["Revenue"])
                - float(r["Acquisition_Cost"]) * float(r["Conversions"]),
                float(r["Acquisition_Cost"]) * float(r["Conversions"]),
            ),
            4,
        ),
    ),
}

dates_valid = all(
    datetime.strptime(row["Date_ISO"], "%Y-%m-%d")
    == datetime.strptime(row["Date"], "%d-%m-%Y")
    for row in processed_rows
)

gold_source_match = (
    len(gold_rows) == 125
    and len({row["Campaign_ID"] for row in gold_rows}) == 125
    and set(row["Campaign_ID"] for row in gold_rows).issubset(raw_by_id)
    and all(
        all(row[field] == raw_by_id[row["Campaign_ID"]][field] for field in raw_fields)
        for row in gold_rows
    )
)

reviewer_1_intents = [row["Reviewer_1_Intent"] for row in gold_rows]
reviewer_2_intents = [row["Reviewer_2_Intent"] for row in gold_rows]
reviewer_1_actions = [row["Reviewer_1_Action"] for row in gold_rows]
reviewer_2_actions = [row["Reviewer_2_Action"] for row in gold_rows]

intent_agreement = np.mean(
    [a == b for a, b in zip(reviewer_1_intents, reviewer_2_intents)]
)
action_agreement = np.mean(
    [a == b for a, b in zip(reviewer_1_actions, reviewer_2_actions)]
)
both_agreement = [
    row["Reviewer_1_Intent"] == row["Reviewer_2_Intent"]
    and row["Reviewer_1_Action"] == row["Reviewer_2_Action"]
    for row in gold_rows
]
status_consistent = all(
    row["Annotation_Status"]
    == ("Agreed" if agreed else "Adjudicated")
    for row, agreed in zip(gold_rows, both_agreement)
)

plan_intents = {"Survival", "Retention", "Growth"}
plan_actions = {"Increase", "Maintain", "Reduce", "Investigate"}
gold_intents = set(row["Adjudicated_Intent"] for row in gold_rows)
gold_actions = set(row["Adjudicated_Action"] for row in gold_rows)

audit = {
    "files": {
        path.name: {"sha256": sha256(path), "bytes": path.stat().st_size}
        for path in (RAW, PROCESSED, GOLD, REVIEW, RULES)
    },
    "raw": {
        "records": len(raw_rows),
        "columns": len(raw_fields),
        "unique_campaign_ids": len({row["Campaign_ID"] for row in raw_rows}),
        "fields": raw_fields,
    },
    "processed": {
        "records": len(processed_rows),
        "columns": len(processed_fields),
        "source_fields_match_raw_exactly": processed_source_match,
        "date_iso_matches_source": dates_valid,
        "maximum_formula_absolute_errors": formula_errors,
        "performance_bands": dict(
            sorted(Counter(row["Performance_Band"] for row in processed_rows).items())
        ),
        "funnel_flags": dict(
            sorted(
                Counter(row["Funnel_Quality_Flag"] for row in processed_rows).items()
            )
        ),
    },
    "gold": {
        "records": len(gold_rows),
        "columns": len(gold_fields),
        "unique_campaign_ids": len({row["Campaign_ID"] for row in gold_rows}),
        "source_fields_match_raw_exactly": gold_source_match,
        "campaign_type_distribution": dict(
            sorted(Counter(row["Campaign_Type"] for row in gold_rows).items())
        ),
        "reviewer_1_intent_distribution": dict(
            sorted(Counter(reviewer_1_intents).items())
        ),
        "reviewer_2_intent_distribution": dict(
            sorted(Counter(reviewer_2_intents).items())
        ),
        "adjudicated_intent_distribution": dict(
            sorted(Counter(row["Adjudicated_Intent"] for row in gold_rows).items())
        ),
        "reviewer_1_action_distribution": dict(
            sorted(Counter(reviewer_1_actions).items())
        ),
        "reviewer_2_action_distribution": dict(
            sorted(Counter(reviewer_2_actions).items())
        ),
        "adjudicated_action_distribution": dict(
            sorted(Counter(row["Adjudicated_Action"] for row in gold_rows).items())
        ),
        "annotation_status_distribution": dict(
            sorted(Counter(row["Annotation_Status"] for row in gold_rows).items())
        ),
        "intent_percent_agreement": float(intent_agreement),
        "action_percent_agreement": float(action_agreement),
        "intent_cohen_kappa": cohen_kappa(reviewer_1_intents, reviewer_2_intents),
        "action_cohen_kappa": cohen_kappa(reviewer_1_actions, reviewer_2_actions),
        "annotation_status_matches_reviewer_agreement": status_consistent,
        "distinct_reviewer_1_notes": len(
            {row["Reviewer_1_Notes"] for row in gold_rows}
        ),
        "distinct_reviewer_2_notes": len(
            {row["Reviewer_2_Notes"] for row in gold_rows}
        ),
        "reviewer_1_rule_based_phrase_count": sum(
            "rule-based interpretation" in row["Reviewer_1_Notes"].lower()
            for row in gold_rows
        ),
        "reviewer_2_rule_based_phrase_count": sum(
            "rule-based interpretation" in row["Reviewer_2_Notes"].lower()
            for row in gold_rows
        ),
        "plan_intent_schema_match": gold_intents.issubset(plan_intents),
        "plan_action_schema_match": gold_actions.issubset(plan_actions),
        "unexpected_plan_intents": sorted(gold_intents.difference(plan_intents)),
        "unexpected_plan_actions": sorted(gold_actions.difference(plan_actions)),
    },
    "confirmatory_ready": False,
    "confirmatory_blockers": [
        "Benchmark intent labels do not use the locked Survival/Retention/Growth schema.",
        "Benchmark action labels do not use the locked Increase/Maintain/Reduce/Investigate schema.",
        "Review documentation describes deterministic disagreements and rule-based interpretations, not independently evidenced human annotations.",
        "Reviewer identities, timestamps and independent-review provenance are absent.",
    ],
}

OUTPUT.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
print(json.dumps(audit, indent=2))
