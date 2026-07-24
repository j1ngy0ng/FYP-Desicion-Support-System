#!/usr/bin/env python3
"""Import the supplied three-layer package while preserving the gold-benchmark gate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


EXPECTED_RAW_SHA256 = (
    "4969a1c5961fba85772822467f87e2c3069107017bdc6d685c21b47a0ed22665"
)
PLAN_INTENTS = {"Survival", "Retention", "Growth"}
PLAN_ACTIONS = {"Increase", "Maintain", "Reduce", "Investigate"}
ANNOTATION_FIELDS = [
    "Reviewer_1_Intent",
    "Reviewer_1_Action",
    "Reviewer_1_Notes",
    "Reviewer_2_Intent",
    "Reviewer_2_Action",
    "Reviewer_2_Notes",
    "Adjudicated_Intent",
    "Adjudicated_Action",
    "Adjudicated_Notes",
    "Annotation_Status",
]


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path(
            r"C:\Users\user\Downloads\nykaa_three_layer_dataset(1)\nykaa_data_layers"
        ),
    )
    parser.add_argument("--destination", type=Path, default=Path("data/layers"))
    args = parser.parse_args()

    raw_path = args.source_dir / "01_raw_dataset_55555x16.csv"
    processed_path = args.source_dir / "02_processed_model_data.csv"
    gold_path = args.source_dir / "03_gold_benchmark_125.csv"
    review_path = args.source_dir / "03_gold_benchmark_review.xlsx"
    dictionary_path = args.source_dir / "BUSINESS_RULES_AND_DATA_DICTIONARY.txt"

    raw_fields, raw_rows = load(raw_path)
    processed_fields, processed_rows = load(processed_path)
    gold_fields, gold_rows = load(gold_path)
    if sha256(raw_path) != EXPECTED_RAW_SHA256:
        raise ValueError("Raw source hash differs from the audited Nykaa source.")
    if len(raw_rows) != 55_555 or len(set(r["Campaign_ID"] for r in raw_rows)) != 55_555:
        raise ValueError("Raw source must contain 55,555 unique campaigns.")
    if len(processed_rows) != len(raw_rows) or processed_fields[: len(raw_fields)] != raw_fields:
        raise ValueError("Processed layer does not preserve the raw schema prefix.")
    for raw, processed in zip(raw_rows, processed_rows):
        if any(raw[field] != processed[field] for field in raw_fields):
            raise ValueError("Processed source fields differ from raw values.")

    raw_by_id = {row["Campaign_ID"]: row for row in raw_rows}
    if len(gold_rows) != 125 or len(set(r["Campaign_ID"] for r in gold_rows)) != 125:
        raise ValueError("Candidate benchmark must contain 125 unique campaigns.")
    for row in gold_rows:
        authentic = raw_by_id.get(row["Campaign_ID"])
        if authentic is None or any(row[field] != authentic[field] for field in raw_fields):
            raise ValueError("Candidate benchmark does not match authentic source values.")

    intents = {row["Adjudicated_Intent"] for row in gold_rows}
    actions = {row["Adjudicated_Action"] for row in gold_rows}
    blockers = []
    if not intents.issubset(PLAN_INTENTS):
        blockers.append(
            "Intent schema differs from Survival/Retention/Growth: "
            + ", ".join(sorted(intents))
        )
    if not actions.issubset(PLAN_ACTIONS):
        blockers.append(
            "Action schema differs from Increase/Maintain/Reduce/Investigate: "
            + ", ".join(sorted(actions))
        )
    blockers.extend(
        [
            "Independent reviewer identities and timestamps are not documented.",
            "Review notes describe deterministic rule-based interpretations.",
        ]
    )

    args.destination.mkdir(parents=True, exist_ok=True)
    copies = {
        raw_path: args.destination / raw_path.name,
        processed_path: args.destination / processed_path.name,
        gold_path: args.destination / "03_gold_benchmark_125_unverified.csv",
        review_path: args.destination / "03_gold_benchmark_review_unverified.xlsx",
        dictionary_path: args.destination / dictionary_path.name,
    }
    for source, destination in copies.items():
        shutil.copy2(source, destination)

    candidate_path = Path("data/benchmark_candidate_125.csv")
    with candidate_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[*raw_fields, *ANNOTATION_FIELDS],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in gold_rows:
            writer.writerow({**raw_by_id[row["Campaign_ID"]], **{f: "" for f in ANNOTATION_FIELDS}})

    audit = {
        "source_directory": str(args.source_dir),
        "raw_sha256": sha256(raw_path),
        "processed_sha256": sha256(processed_path),
        "unverified_gold_sha256": sha256(gold_path),
        "review_workbook_sha256": sha256(review_path),
        "raw_records": len(raw_rows),
        "processed_records": len(processed_rows),
        "candidate_benchmark_records": len(gold_rows),
        "raw_fields_preserved_in_processed": True,
        "candidate_source_fields_match_raw": True,
        "candidate_output": str(candidate_path),
        "gold_promoted_to_audited_benchmark": False,
        "confirmatory_ready": False,
        "confirmatory_blockers": blockers,
    }
    (args.destination / "IMPORT_AUDIT.json").write_text(
        json.dumps(audit, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
