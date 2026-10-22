"""Prepare model-blinded, held-out campaign cases for independent action review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


SELECTION_SALT = "additional-heldout-action-review-v1"
INTENTS = ("Survival", "Retention", "Growth")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_dates(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    dates = frame["Date"].astype(str).str.strip().str.replace("/", "-", regex=False)
    if dates.str.match(r"^\d{4}-\d{1,2}-\d{1,2}$").all():
        frame["Date"] = pd.to_datetime(dates, format="%Y-%m-%d", errors="raise")
    elif dates.str.match(r"^\d{1,2}-\d{1,2}-\d{4}$").all():
        frame["Date"] = pd.to_datetime(dates, format="%d-%m-%Y", errors="raise")
    else:
        raise ValueError("Date must consistently use YYYY-M-D or D-M-YYYY format.")
    return frame.sort_values(["Date", "Campaign_ID"]).reset_index(drop=True)


def prepare(
    source: Path,
    active_dataset: Path,
    benchmark: Path,
    count: int,
) -> tuple[pd.DataFrame, dict]:
    data = pd.read_csv(source).drop_duplicates().copy()
    data = parse_dates(data)
    active = parse_dates(pd.read_csv(active_dataset).drop_duplicates())

    holdout_start = max(1, int(len(data) * 0.85))
    holdout = data.iloc[holdout_start:].copy()
    benchmark_ids = set(pd.read_csv(benchmark)["Campaign_ID"].astype(str))
    active_ids = set(active["Campaign_ID"].astype(str))
    excluded_ids = benchmark_ids.union(active_ids)
    eligible = holdout.loc[
        ~holdout["Campaign_ID"].astype(str).isin(excluded_ids)
    ].copy()
    eligible["_selection_key"] = eligible["Campaign_ID"].astype(str).map(
        lambda value: hashlib.sha256(
            f"{SELECTION_SALT}|{value}".encode("utf-8")
        ).hexdigest()
    )
    eligible = eligible.sort_values("_selection_key").head(count).reset_index(drop=True)
    if len(eligible) != count:
        raise RuntimeError(f"Needed {count} eligible cases but found {len(eligible)}.")

    eligible.insert(0, "Review_Case_ID", [f"EXT-{index:03d}" for index in range(1, count + 1)])
    eligible["Assigned_Intent"] = [INTENTS[index % len(INTENTS)] for index in range(count)]
    eligible["Date"] = eligible["Date"].dt.strftime("%d-%m-%Y")
    eligible["Source_Partition"] = "Chronological final 15% CampaignNet holdout"
    eligible["Selection_Status"] = "Pending two independent human reviews and adjudication"
    eligible = eligible.drop(columns=["_selection_key"])

    selected_ids = set(eligible["Campaign_ID"].astype(str))
    train_ids = set(active.iloc[: int(len(active) * 0.70)]["Campaign_ID"].astype(str))
    assert not selected_ids.intersection(train_ids), "Selected case overlaps CampaignNet training partition."
    assert not selected_ids.intersection(benchmark_ids), "Selected case overlaps the 125-case benchmark."
    assert not selected_ids.intersection(active_ids), "Selected case overlaps the active decision dataset."
    assert eligible["Campaign_ID"].is_unique, "Selected Campaign_ID values are not unique."

    manifest = {
        "status": "PENDING_HUMAN_REVIEW",
        "source_dataset": str(source.resolve()),
        "source_dataset_sha256": sha256(source),
        "active_decision_dataset": str(active_dataset.resolve()),
        "active_decision_dataset_sha256": sha256(active_dataset),
        "existing_benchmark": str(benchmark.resolve()),
        "existing_benchmark_sha256": sha256(benchmark),
        "source_record_count_after_exact_deduplication": int(len(data)),
        "active_decision_case_count": int(len(active)),
        "campaignnet_train_count": int(len(active) * 0.70),
        "candidate_holdout_count": int(len(holdout)),
        "eligible_after_benchmark_exclusion": int(
            (~holdout["Campaign_ID"].astype(str).isin(excluded_ids)).sum()
        ),
        "selected_case_count": count,
        "selection_salt": SELECTION_SALT,
        "selection_method": "Sort the untouched chronological final-15% records by SHA-256(salt|Campaign_ID), exclude all IDs in the existing 125-case benchmark, and take the first requested count.",
        "intent_assignment": "Assigned before review in repeating Survival, Retention, Growth order after deterministic selection.",
        "model_outputs_exposed_to_reviewers": False,
        "evaluation_eligibility": "Only after two independent reviews, disagreement adjudication, frozen acceptable-action sets, and validation.",
        "same_source_limitation": "The additional cases are unused records from the same public source dataset; they are not an external-dataset validation cohort.",
        "selected_campaign_ids": eligible["Campaign_ID"].astype(str).tolist(),
    }
    return eligible, manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/layers/01_raw_dataset_55555x16.csv"),
    )
    parser.add_argument(
        "--active-dataset", type=Path, default=Path("data/Dataset.csv")
    )
    parser.add_argument("--benchmark", type=Path, default=Path("data/benchmark_audited.csv"))
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    cases, manifest = prepare(
        args.source, args.active_dataset, args.benchmark, args.count
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases.to_csv(args.output_dir / "additional_heldout_cases.csv", index=False)
    (args.output_dir / "additional_heldout_cases.json").write_text(
        json.dumps(cases.where(pd.notna(cases), None).to_dict("records"), indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "selection_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"selected={len(cases)}")
    print(f"output={args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
