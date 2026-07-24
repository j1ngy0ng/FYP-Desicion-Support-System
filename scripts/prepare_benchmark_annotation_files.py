#!/usr/bin/env python3
"""Create plan-aligned independent-review files from the 125 candidate cases."""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "data" / "benchmark_candidate_125.csv"
RAW_FIELDS = [
    "Campaign_ID", "Campaign_Type", "Target_Audience", "Duration",
    "Channel_Used", "Impressions", "Clicks", "Leads", "Conversions",
    "Revenue", "Acquisition_Cost", "ROI", "Language", "Engagement_Score",
    "Customer_Segment", "Date",
]
REVIEWER_FIELDS = ["Reviewer_Intent", "Reviewer_Action", "Reviewer_Notes"]
AUDIT_FIELDS = [
    "Reviewer_1_Intent", "Reviewer_1_Action", "Reviewer_1_Notes",
    "Reviewer_2_Intent", "Reviewer_2_Action", "Reviewer_2_Notes",
    "Adjudicated_Intent", "Adjudicated_Action", "Adjudicated_Notes",
    "Annotation_Status",
]


def read_rows() -> list[dict[str, str]]:
    with CANDIDATE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 125 or len({row["Campaign_ID"] for row in rows}) != 125:
        raise ValueError("Candidate benchmark must contain 125 unique cases.")
    return rows


def write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def reviewer_rows(rows: list[dict[str, str]], seed: int) -> list[dict[str, str]]:
    prepared = [
        {
            **{field: row[field] for field in RAW_FIELDS},
            **{field: "" for field in REVIEWER_FIELDS},
        }
        for row in rows
    ]
    random.Random(seed).shuffle(prepared)
    return prepared


def main() -> None:
    rows = read_rows()
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["Campaign_Type"]].append(row)
    if set(map(len, grouped.values())) != {25}:
        raise ValueError("Expected 25 candidate cases for each campaign type.")

    pilot: list[dict[str, str]] = []
    pilot_rng = random.Random(20260405)
    for campaign_type in sorted(grouped):
        pilot.extend(pilot_rng.sample(grouped[campaign_type], 5))

    audited_rows = [
        {
            **{field: row[field] for field in RAW_FIELDS},
            **{field: "" for field in AUDIT_FIELDS},
        }
        for row in rows
    ]
    pilot_audited = [
        {
            **{field: row[field] for field in RAW_FIELDS},
            **{field: "" for field in AUDIT_FIELDS},
        }
        for row in pilot
    ]

    write(ROOT / "data" / "benchmark_annotation_template.csv", [*RAW_FIELDS, *AUDIT_FIELDS], audited_rows)
    write(ROOT / "data" / "pilot_annotation_template.csv", [*RAW_FIELDS, *AUDIT_FIELDS], pilot_audited)
    write(ROOT / "data" / "benchmark_reviewer_1.csv", [*RAW_FIELDS, *REVIEWER_FIELDS], reviewer_rows(rows, 101))
    write(ROOT / "data" / "benchmark_reviewer_2.csv", [*RAW_FIELDS, *REVIEWER_FIELDS], reviewer_rows(rows, 202))
    write(ROOT / "data" / "pilot_reviewer_1.csv", [*RAW_FIELDS, *REVIEWER_FIELDS], reviewer_rows(pilot, 303))
    write(ROOT / "data" / "pilot_reviewer_2.csv", [*RAW_FIELDS, *REVIEWER_FIELDS], reviewer_rows(pilot, 404))
    print("Prepared 25-case pilot and 125-case independent-review files.")


if __name__ == "__main__":
    main()
