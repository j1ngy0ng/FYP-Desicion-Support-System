#!/usr/bin/env python3
"""Validate and canonicalise a user-provided single-reviewer annotation dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


ANNOTATION_FIELDS = ("Reviewer_Intent", "Reviewer_Action", "Reviewer_Notes")
NUMERIC_FIELDS = {
    "Duration",
    "Impressions",
    "Clicks",
    "Leads",
    "Conversions",
    "Revenue",
    "Acquisition_Cost",
    "ROI",
    "Engagement_Score",
}
INTENTS = {"Survival", "Retention", "Growth"}
ACTIONS = {"Increase", "Maintain", "Decrease", "Investigate"}
ANNOTATION_SOURCE = (
    "User-provided as human annotation; reviewer independence and adjudication not documented"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def parse_date(value: str) -> datetime:
    normalized = value.strip().replace("/", "-")
    for pattern in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, pattern)
        except ValueError:
            pass
    raise ValueError(f"Unsupported date value: {value}")


def semantically_equal(field: str, supplied: str, authentic: str) -> bool:
    if field == "Date":
        return parse_date(supplied) == parse_date(authentic)
    if field in NUMERIC_FIELDS:
        try:
            return Decimal(supplied.strip()) == Decimal(authentic.strip())
        except InvalidOperation as exc:
            raise ValueError(f"Invalid numeric value in {field}: {supplied}") from exc
    return supplied == authentic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(
            r"C:\Users\user\Downloads\Dataset_development_human_annotated_v2.csv"
        ),
    )
    parser.add_argument(
        "--authentic-source",
        type=Path,
        default=Path("data/raw/nykaa_campaign_data.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/Dataset_human_provided_development.csv"),
    )
    parser.add_argument(
        "--source-copy-dir",
        type=Path,
        default=Path("data/human_annotations/source"),
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("data/human_annotation_dataset_audit.json"),
    )
    args = parser.parse_args()

    source_fields, authentic_rows = load(args.authentic_source)
    supplied_fields, supplied_rows = load(args.input)
    expected_fields = [*source_fields, *ANNOTATION_FIELDS]
    if supplied_fields != expected_fields:
        raise ValueError(
            "Expected the authentic 16 columns followed by Reviewer_Intent, "
            "Reviewer_Action and Reviewer_Notes."
        )
    if len(supplied_rows) != len(authentic_rows):
        raise ValueError("Supplied and authentic datasets must have the same row count.")

    authentic_by_id = {row["Campaign_ID"]: row for row in authentic_rows}
    supplied_ids = [row["Campaign_ID"] for row in supplied_rows]
    if len(set(supplied_ids)) != len(supplied_ids):
        raise ValueError("Supplied Campaign_ID values must be unique.")
    if set(supplied_ids) != set(authentic_by_id):
        raise ValueError("Supplied Campaign_ID coverage differs from the authentic source.")

    canonical_rows: list[dict[str, str]] = []
    intent_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    note_counts: Counter[str] = Counter()
    for supplied in supplied_rows:
        authentic = authentic_by_id[supplied["Campaign_ID"]]
        for field in source_fields:
            if not semantically_equal(field, supplied[field], authentic[field]):
                raise ValueError(
                    f"Source value mismatch for {supplied['Campaign_ID']} field {field}."
                )
        intent = supplied["Reviewer_Intent"].strip().title()
        action = supplied["Reviewer_Action"].strip().title()
        notes = supplied["Reviewer_Notes"].strip()
        if intent not in INTENTS:
            raise ValueError(f"Unsupported reviewer intent: {intent}")
        if action not in ACTIONS:
            raise ValueError(f"Unsupported reviewer action: {action}")
        if not notes:
            raise ValueError(f"Blank Reviewer_Notes for {supplied['Campaign_ID']}.")
        intent_counts[intent] += 1
        action_counts[action] += 1
        note_counts[notes] += 1
        canonical_rows.append(
            {
                **authentic,
                "Reviewer_Intent": intent,
                "Reviewer_Action": action,
                "Reviewer_Notes": notes,
                "Annotation_Source": ANNOTATION_SOURCE,
                "Annotation_Status": "DevelopmentOnly",
            }
        )

    args.source_copy_dir.mkdir(parents=True, exist_ok=True)
    preserved_source = args.source_copy_dir / args.input.name
    shutil.copy2(args.input, preserved_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_fields = [
        *source_fields,
        *ANNOTATION_FIELDS,
        "Annotation_Source",
        "Annotation_Status",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(canonical_rows)

    missing_actions = sorted(ACTIONS.difference(action_counts))
    blockers = [
        "Only one reviewer field set is present.",
        "Reviewer identity, independence and annotation timestamps are not documented.",
        "No adjudication fields or audited status are present.",
    ]
    if missing_actions:
        blockers.append(
            "Action-class coverage is incomplete; missing: " + ", ".join(missing_actions)
        )
    most_repeated_note, repeated_count = note_counts.most_common(1)[0]
    audit = {
        "input_file": str(args.input),
        "input_sha256": sha256(args.input),
        "preserved_source_copy": str(preserved_source),
        "canonical_output": str(args.output),
        "canonical_output_sha256": sha256(args.output),
        "authentic_source": str(args.authentic_source),
        "records": len(canonical_rows),
        "unique_campaign_ids": len(set(supplied_ids)),
        "source_attributes_semantically_match": True,
        "intent_distribution": dict(sorted(intent_counts.items())),
        "action_distribution": dict(sorted(action_counts.items())),
        "distinct_notes": len(note_counts),
        "most_repeated_note_count": repeated_count,
        "most_repeated_note": most_repeated_note,
        "annotation_source": ANNOTATION_SOURCE,
        "annotation_status": "DevelopmentOnly",
        "confirmatory_ready": False,
        "confirmatory_blockers": blockers,
    }
    args.audit.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
