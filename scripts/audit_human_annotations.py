#!/usr/bin/env python3
"""Merge independent reviewer files and validate the final human benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter
from pathlib import Path


INTENTS = {"Survival", "Retention", "Growth"}
ACTIONS = {"Increase", "Maintain", "Reduce", "Investigate"}
REVIEW_FIELDS = {"Campaign_ID", "Reviewer_Intent", "Reviewer_Action", "Reviewer_Notes"}


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def kappa(left: list[str], right: list[str]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Kappa requires two non-empty, equally sized label lists.")
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_counts, right_counts = Counter(left), Counter(right)
    expected = sum(
        left_counts[label] / len(left) * right_counts[label] / len(right)
        for label in set(left_counts) | set(right_counts)
    )
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def validate_review(rows: list[dict[str, str]], path: Path) -> None:
    if not rows or not REVIEW_FIELDS.issubset(rows[0]):
        raise ValueError(f"{path} is not a reviewer form.")
    if len({row["Campaign_ID"] for row in rows}) != len(rows):
        raise ValueError(f"{path} contains duplicate Campaign_ID values.")
    for row in rows:
        if row["Reviewer_Intent"].strip() not in INTENTS:
            raise ValueError(f"{path}: invalid or blank intent for {row['Campaign_ID']}.")
        if row["Reviewer_Action"].strip() not in ACTIONS:
            raise ValueError(f"{path}: invalid or blank action for {row['Campaign_ID']}.")


def merge_reviews(first_path: Path, second_path: Path, output: Path) -> dict[str, float | int]:
    first, second = read(first_path), read(second_path)
    validate_review(first, first_path)
    validate_review(second, second_path)
    second_by_id = {row["Campaign_ID"]: row for row in second}
    if set(second_by_id) != {row["Campaign_ID"] for row in first}:
        raise ValueError("Reviewer files do not contain the same campaign IDs.")
    fields = [
        key for key in first[0] if key not in {"Reviewer_Intent", "Reviewer_Action", "Reviewer_Notes"}
    ] + [
        "Reviewer_1_Intent", "Reviewer_1_Action", "Reviewer_1_Notes",
        "Reviewer_2_Intent", "Reviewer_2_Action", "Reviewer_2_Notes",
        "Adjudicated_Intent", "Adjudicated_Action", "Adjudicator_Notes",
        "Annotation_Status",
    ]
    merged = []
    for row in first:
        other = second_by_id[row["Campaign_ID"]]
        base = {
            key: value for key, value in row.items()
            if key not in {"Reviewer_Intent", "Reviewer_Action", "Reviewer_Notes"}
        }
        merged.append({
            **base,
            "Reviewer_1_Intent": row["Reviewer_Intent"].strip(),
            "Reviewer_1_Action": row["Reviewer_Action"].strip(),
            "Reviewer_1_Notes": row["Reviewer_Notes"].strip(),
            "Reviewer_2_Intent": other["Reviewer_Intent"].strip(),
            "Reviewer_2_Action": other["Reviewer_Action"].strip(),
            "Reviewer_2_Notes": other["Reviewer_Notes"].strip(),
            "Adjudicated_Intent": "",
            "Adjudicated_Action": "",
            "Adjudicator_Notes": "",
            "Annotation_Status": "",
        })
    write(output, merged, fields)
    result = {
        "cases": len(merged),
        "intent_kappa": kappa(
            [row["Reviewer_1_Intent"] for row in merged],
            [row["Reviewer_2_Intent"] for row in merged],
        ),
        "action_kappa": kappa(
            [row["Reviewer_1_Action"] for row in merged],
            [row["Reviewer_2_Action"] for row in merged],
        ),
        "action_disagreements": sum(
            row["Reviewer_1_Action"] != row["Reviewer_2_Action"] for row in merged
        ),
    }
    return result


def finalize(adjudication_path: Path, output: Path) -> dict[str, float | int]:
    rows = read(adjudication_path)
    if len(rows) < 120:
        raise ValueError("At least 120 audited cases are required.")
    forbidden = {
        "Intent", "Reference_Action", "Justification",
        "Reviewer_1_Label", "Reviewer_2_Label",
    }
    if forbidden.intersection(rows[0]):
        raise ValueError("Legacy generated annotation columns are forbidden.")
    for row in rows:
        if row["Adjudicated_Intent"].strip() not in INTENTS:
            raise ValueError(f"Invalid adjudicated intent for {row['Campaign_ID']}.")
        if row["Adjudicated_Action"].strip() not in ACTIONS:
            raise ValueError(f"Invalid adjudicated action for {row['Campaign_ID']}.")
        if row["Annotation_Status"].strip() != "Audited":
            raise ValueError(f"{row['Campaign_ID']} is not marked Audited.")
    action_kappa = kappa(
        [row["Reviewer_1_Action"] for row in rows],
        [row["Reviewer_2_Action"] for row in rows],
    )
    if action_kappa < .60:
        raise ValueError(f"Action-label Cohen's kappa is {action_kappa:.3f}; minimum is 0.60.")
    shutil.copyfile(adjudication_path, output)
    return {"cases": len(rows), "action_kappa": action_kappa}


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    merge = subparsers.add_parser("merge")
    merge.add_argument("reviewer_1", type=Path)
    merge.add_argument("reviewer_2", type=Path)
    merge.add_argument("--output", type=Path, default=Path("data/benchmark_adjudication.csv"))
    finish = subparsers.add_parser("finalize")
    finish.add_argument("adjudication", type=Path)
    finish.add_argument("--output", type=Path, default=Path("data/benchmark_audited.csv"))
    args = parser.parse_args()
    result = (
        merge_reviews(args.reviewer_1, args.reviewer_2, args.output)
        if args.command == "merge"
        else finalize(args.adjudication, args.output)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
