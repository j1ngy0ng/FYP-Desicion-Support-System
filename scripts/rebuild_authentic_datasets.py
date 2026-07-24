#!/usr/bin/env python3
"""Rebuild project datasets without AI-generated decision annotations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
from datetime import datetime
from pathlib import Path


SOURCE_COLUMNS = [
    "Campaign_ID",
    "Campaign_Type",
    "Target_Audience",
    "Duration",
    "Channel_Used",
    "Impressions",
    "Clicks",
    "Leads",
    "Conversions",
    "Revenue",
    "Acquisition_Cost",
    "ROI",
    "Language",
    "Engagement_Score",
    "Customer_Segment",
    "Date",
]

ANNOTATION_COLUMNS = [
    "Reviewer_1_Intent",
    "Reviewer_1_Action",
    "Reviewer_1_Notes",
    "Reviewer_2_Intent",
    "Reviewer_2_Action",
    "Reviewer_2_Notes",
    "Adjudicated_Intent",
    "Adjudicated_Action",
    "Adjudicator_Notes",
    "Annotation_Status",
]

REVIEW_FORM_COLUMNS = ["Reviewer_Intent", "Reviewer_Action", "Reviewer_Notes"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows({column: row.get(column, "") for column in columns} for row in rows)


def normalise_date(value: str) -> str:
    for pattern in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date value: {value!r}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / "Downloads" / "nykaa_campaign_data (2).csv",
    )
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    root = args.project_root.resolve()
    source = args.source.resolve()
    active_path = root / "data" / "Dataset.csv"
    stress_path = root / "data" / "Dataset_conflict_stress.csv"
    raw_copy = root / "data" / "raw" / "nykaa_campaign_data.csv"

    original = read_csv(source)
    if not original or list(original[0]) != SOURCE_COLUMNS:
        raise ValueError("The source file does not match the expected 16-column Nykaa schema.")
    if len({row["Campaign_ID"] for row in original}) != len(original):
        raise ValueError("Source Campaign_ID values are not unique.")

    previous_active = read_csv(active_path)
    selected_ids = [row["Campaign_ID"] for row in previous_active]
    if len(selected_ids) != 125 or len(set(selected_ids)) != 125:
        raise ValueError("The existing decision-case selection must contain 125 unique campaign IDs.")

    source_by_id = {row["Campaign_ID"]: row for row in original}
    missing = [campaign_id for campaign_id in selected_ids if campaign_id not in source_by_id]
    if missing:
        raise ValueError(f"{len(missing)} selected campaign IDs are absent from the source file.")

    selected = []
    for campaign_id in selected_ids:
        row = {column: source_by_id[campaign_id][column] for column in SOURCE_COLUMNS}
        row["Date"] = normalise_date(row["Date"])
        selected.append(row)

    write_csv(active_path, selected, SOURCE_COLUMNS)

    annotation_rows = [
        {**row, **{column: "" for column in ANNOTATION_COLUMNS}}
        for row in selected
    ]
    write_csv(
        root / "data" / "benchmark_annotation_template.csv",
        annotation_rows,
        SOURCE_COLUMNS + ANNOTATION_COLUMNS,
    )

    pilot_rows = list(annotation_rows)
    random.Random(20260405).shuffle(pilot_rows)
    pilot_rows = pilot_rows[:25]
    pilot_ids = {row["Campaign_ID"] for row in pilot_rows}
    write_csv(
        root / "data" / "pilot_annotation_template.csv",
        pilot_rows,
        SOURCE_COLUMNS + ANNOTATION_COLUMNS,
    )

    reviewer_1 = [
        {**row, **{column: "" for column in REVIEW_FORM_COLUMNS}}
        for row in selected
    ]
    reviewer_2 = list(reviewer_1)
    random.Random(20260406).shuffle(reviewer_1)
    random.Random(20260407).shuffle(reviewer_2)
    write_csv(
        root / "data" / "benchmark_reviewer_1.csv",
        reviewer_1,
        SOURCE_COLUMNS + REVIEW_FORM_COLUMNS,
    )
    write_csv(
        root / "data" / "benchmark_reviewer_2.csv",
        reviewer_2,
        SOURCE_COLUMNS + REVIEW_FORM_COLUMNS,
    )
    write_csv(
        root / "data" / "pilot_reviewer_1.csv",
        [row for row in reviewer_1 if row["Campaign_ID"] in pilot_ids],
        SOURCE_COLUMNS + REVIEW_FORM_COLUMNS,
    )
    write_csv(
        root / "data" / "pilot_reviewer_2.csv",
        [row for row in reviewer_2 if row["Campaign_ID"] in pilot_ids],
        SOURCE_COLUMNS + REVIEW_FORM_COLUMNS,
    )

    if stress_path.exists():
        stress_rows = read_csv(stress_path)
        write_csv(
            stress_path,
            [{column: row.get(column, "") for column in SOURCE_COLUMNS} for row in stress_rows],
            SOURCE_COLUMNS,
        )

    raw_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, raw_copy)

    dates = [datetime.strptime(row["Date"], "%d-%m-%Y").date() for row in original]
    channels = sorted(
        {
            channel.strip()
            for row in original
            for channel in row["Channel_Used"].split(",")
            if channel.strip()
        }
    )
    audit = {
        "source_file": str(raw_copy.relative_to(root)).replace("\\", "/"),
        "source_sha256": sha256(raw_copy),
        "records": len(original),
        "columns": len(SOURCE_COLUMNS),
        "campaign_ids_unique": len({row["Campaign_ID"] for row in original}),
        "atomic_channels": channels,
        "date_min": min(dates).isoformat(),
        "date_max": max(dates).isoformat(),
        "monthly_periods": len({(value.year, value.month) for value in dates}),
        "downstream_outcomes": ["Conversions", "Revenue", "Acquisition_Cost", "ROI"],
        "decision_cases_selected": len(selected),
        "synthetic_annotation_columns_removed": [
            "Intent",
            "Reference_Action",
            "Justification",
            "Reviewer_1_Label",
            "Reviewer_2_Label",
        ],
        "human_annotations_complete": False,
    }
    (root / "data" / "source_audit.json").write_text(
        json.dumps(audit, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
