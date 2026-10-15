"""Create the anonymised, participant-clustered human-study evidence package."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


CONDITIONS = {
    "raw_uncalibrated": "H1: Raw-Uncalibrated",
    "calibrated_confidence": "H2: Calibrated-Confidence Only",
    "structured_uncalibrated": "H3: Structured-Uncalibrated",
    "terse_calibrated": "H4: Terse-Calibrated",
    "structured_calibrated": "H5: Structured-Calibrated No Caveat",
    "full_framework": "H6: Complete Calibrated DIAC",
}

METRICS = [
    "actionability",
    "specificity",
    "feasibility",
    "explanation_usefulness",
    "reliance",
    "willingness_to_review",
    "user_acceptance",
    "trust_alignment",
    "decision_time_seconds",
]

CONTRASTS = [
    ("H2-H1", "calibrated_confidence", "raw_uncalibrated"),
    ("H3-H1", "structured_uncalibrated", "raw_uncalibrated"),
    ("H6-H3", "full_framework", "structured_uncalibrated"),
    ("H6-H2", "full_framework", "calibrated_confidence"),
    ("H5-H4", "structured_calibrated", "terse_calibrated"),
    ("H6-H5", "full_framework", "structured_calibrated"),
    ("H6-H4", "full_framework", "terse_calibrated"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile_ci(values: np.ndarray) -> tuple[float, float]:
    low, high = np.quantile(values, [0.025, 0.975])
    return float(low), float(high)


def bootstrap_mean(values: np.ndarray, rng: np.random.Generator, iterations: int) -> tuple[float, float]:
    samples = rng.choice(values, size=(iterations, len(values)), replace=True).mean(axis=1)
    return percentile_ci(samples)


def write_markdown(path: Path, audit: dict, condition_summary: pd.DataFrame) -> None:
    lines = [
        "# Human Study Data Audit and Protocol Deviations",
        "",
        "The analysis uses all complete consented records in the corrected frozen database. No outcome response was changed or removed after outcomes were inspected.",
        "",
        "## Verified dataset",
        "",
        f"- Complete participants: {audit['participants']}",
        f"- Responses: {audit['responses']}",
        f"- Complete nine-trial blocks: {audit['complete_participants']}",
        f"- Missing required values: {audit['missing_required_values']}",
        f"- Duplicate participant-case records: {audit['duplicate_participant_cases']}",
        f"- Consent-confirmed responses: {audit['consent_confirmed_responses']}",
        "",
        "## Deviations and interpretation limits",
        "",
        "- The participant groups contain eight confirmed marketing practitioners and ten non-practitioners.",
        "- Counterbalancing sequences are uneven and CB-3 has no participant. Condition exposure is nevertheless between 25 and 29 trials per condition. Report the sequence imbalance as a protocol deviation.",
        "- Two complete participant blocks pre-date the main October collection period. Their provenance must be checked against the recruitment log before final submission; they remain included because no pre-specified exclusion evidence is present in the database.",
        f"- The median recorded total response time was {audit['median_recorded_total_seconds']:.1f} seconds for nine trials. {audit['participants_under_120_seconds']} participants recorded less than 120 seconds. This is a data-quality signal, not a post-hoc exclusion rule.",
        f"- The largest repeated seven-rating-and-decision response vector occurred {audit['largest_identical_response_vector']} times within one condition. This pattern requires transparent discussion and source verification before strong human-effect claims.",
        "- Because the study is formative and small, comparisons are descriptive. Participant-clustered bootstrap intervals quantify uncertainty but are not population-level effectiveness claims.",
        "",
        "## Condition exposure",
        "",
        "| Condition | Trials | Participants |",
        "|---|---:|---:|",
    ]
    for row in condition_summary.itertuples(index=False):
        lines.append(f"| {row.condition_label} | {row.trials} | {row.participants} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(f"file:{args.db.resolve()}?mode=ro", uri=True)
    responses = pd.read_sql_query(
        "SELECT * FROM human_study_responses ORDER BY created_at, id", connection
    )
    connection.close()
    if responses.empty:
        raise SystemExit("No human-study responses found")

    responses["created_at"] = pd.to_datetime(responses["created_at"])
    first_seen = responses.groupby("participant_code")["created_at"].min().sort_values()
    aliases = {code: f"P{index:03d}" for index, code in enumerate(first_seen.index, 1)}
    responses["participant_id"] = responses["participant_code"].map(aliases)
    responses["condition_label"] = responses["condition"].map(CONDITIONS)
    responses["decision_time_seconds"] = responses["decision_time_ms"] / 1000
    responses["reliance_normalised"] = (responses["reliance"] - 1) / 4
    responses["trust_alignment_gap"] = (
        responses["reliance_normalised"] - responses["correct"].astype(float)
    ).abs()
    responses["trust_alignment"] = 1 - responses["trust_alignment_gap"]
    responses["incorrect_uncritical_acceptance"] = (
        (responses["correct"] == 0)
        & (responses["decision"] == "Accept without checking")
    ).astype(int)
    responses["at_risk"] = ((responses["correct"] == 0) | (responses["low_confidence"] == 1)).astype(int)
    responses["at_risk_uncritical_acceptance"] = (
        (responses["at_risk"] == 1)
        & (responses["decision"] == "Accept without checking")
    ).astype(int)

    public_columns = [
        "participant_id", "participant_group", "campaign_id", "condition",
        "condition_label", "presentation_order", "counterbalance_group",
        "recommended_action", "confidence", "correct", "low_confidence",
        "actionability", "specificity", "feasibility", "explanation_usefulness",
        "reliance", "reliance_normalised", "willingness_to_review",
        "user_acceptance", "decision", "decision_time_seconds",
        "trust_alignment_gap", "trust_alignment", "incorrect_uncritical_acceptance",
        "at_risk", "at_risk_uncritical_acceptance", "consent_confirmed", "created_at",
    ]
    responses[public_columns].to_csv(
        args.output / "analysis_ready_responses.csv", index=False, encoding="utf-8-sig"
    )

    participant = responses.groupby("participant_id").agg(
        participant_group=("participant_group", "first"),
        responses=("id", "size"),
        distinct_cases=("campaign_id", "nunique"),
        consented=("consent_confirmed", "sum"),
        counterbalance_group=("counterbalance_group", "first"),
        first_response=("created_at", "min"),
        last_response=("created_at", "max"),
        recorded_total_seconds=("decision_time_seconds", "sum"),
    ).reset_index()
    participant["session_span_seconds"] = (
        participant["last_response"] - participant["first_response"]
    ).dt.total_seconds()
    participant["complete"] = (
        (participant["responses"] == 9)
        & (participant["distinct_cases"] == 9)
        & (participant["consented"] == 9)
    )
    participant["earlier_collection_date_flag"] = (
        participant["first_response"] < pd.Timestamp("2026-10-11")
    )
    participant.to_csv(args.output / "participant_audit.csv", index=False, encoding="utf-8-sig")

    rng = np.random.default_rng(args.seed)
    summary_rows = []
    ci_rows = []
    for condition, label in CONDITIONS.items():
        subset = responses[responses["condition"] == condition]
        summary_rows.append({
            "condition": condition,
            "condition_label": label,
            "trials": len(subset),
            "participants": subset["participant_id"].nunique(),
            "correct_trials": int(subset["correct"].sum()),
            "incorrect_trials": int((subset["correct"] == 0).sum()),
            "incorrect_accepted_without_checking": int(
                subset["incorrect_uncritical_acceptance"].sum()
            ),
        })
        participant_means = subset.groupby("participant_id")[METRICS].mean()
        for metric in METRICS:
            values = participant_means[metric].to_numpy(float)
            low, high = bootstrap_mean(values, rng, args.bootstrap)
            ci_rows.append({
                "condition": condition,
                "condition_label": label,
                "metric": metric,
                "participant_weighted_mean": float(values.mean()),
                "cluster_bootstrap_ci_low": low,
                "cluster_bootstrap_ci_high": high,
                "participants": len(values),
                "trials": len(subset),
                "trial_weighted_mean": float(subset[metric].mean()),
            })
    condition_summary = pd.DataFrame(summary_rows)
    condition_summary.to_csv(args.output / "condition_exposure.csv", index=False, encoding="utf-8-sig")
    ci_frame = pd.DataFrame(ci_rows)
    ci_frame.to_csv(args.output / "condition_metrics_clustered.csv", index=False, encoding="utf-8-sig")

    contrast_rows = []
    participant_condition = responses.groupby(["participant_id", "condition"])[METRICS].mean()
    for contrast, left, right in CONTRASTS:
        for metric in METRICS:
            left_values = participant_condition[metric].unstack("condition")[left]
            right_values = participant_condition[metric].unstack("condition")[right]
            difference = (left_values - right_values).dropna().to_numpy(float)
            low, high = bootstrap_mean(difference, rng, args.bootstrap)
            contrast_rows.append({
                "contrast": contrast,
                "left_condition": CONDITIONS[left],
                "right_condition": CONDITIONS[right],
                "metric": metric,
                "mean_paired_difference": float(difference.mean()),
                "cluster_bootstrap_ci_low": low,
                "cluster_bootstrap_ci_high": high,
                "participants": len(difference),
                "interpretation": "descriptive; positive favours left condition",
            })
    pd.DataFrame(contrast_rows).to_csv(
        args.output / "planned_condition_contrasts.csv", index=False, encoding="utf-8-sig"
    )

    incorrect = responses[responses["correct"] == 0]
    at_risk = responses[responses["at_risk"] == 1]
    incorrect_summary = pd.DataFrame([
        {"measure": "Incorrect recommendation trials", "value": len(incorrect)},
        {"measure": "Participants exposed to an incorrect recommendation", "value": incorrect["participant_id"].nunique()},
        {"measure": "Incorrect recommendations accepted without checking", "value": int(incorrect["incorrect_uncritical_acceptance"].sum())},
        {"measure": "Incorrect uncritical acceptance rate", "value": float(incorrect["incorrect_uncritical_acceptance"].mean())},
        {"measure": "Mean reliance on incorrect recommendations", "value": float(incorrect["reliance"].mean())},
        {"measure": "Mean willingness to review incorrect recommendations", "value": float(incorrect["willingness_to_review"].mean())},
        {"measure": "At-risk trials (incorrect or low confidence)", "value": len(at_risk)},
        {"measure": "At-risk recommendations accepted without checking", "value": int(at_risk["at_risk_uncritical_acceptance"].sum())},
        {"measure": "At-risk uncritical acceptance rate", "value": float(at_risk["at_risk_uncritical_acceptance"].mean())},
    ])
    incorrect_summary.to_csv(args.output / "incorrect_recommendation_analysis.csv", index=False, encoding="utf-8-sig")

    decision_distribution = (
        responses.groupby(["condition_label", "decision"]).size().rename("count").reset_index()
    )
    decision_distribution["within_condition_rate"] = decision_distribution["count"] / decision_distribution.groupby("condition_label")["count"].transform("sum")
    decision_distribution.to_csv(args.output / "decision_distribution.csv", index=False, encoding="utf-8-sig")

    rating_vector = [
        "condition", "actionability", "specificity", "feasibility",
        "explanation_usefulness", "reliance", "willingness_to_review",
        "user_acceptance", "decision",
    ]
    repeated = responses.groupby(rating_vector).size()
    missing_required = int(responses[public_columns[:-1]].isna().sum().sum())
    duplicates = int(responses.duplicated(["participant_code", "campaign_id"]).sum())
    audit = {
        "source_database_sha256": sha256(args.db),
        "responses": int(len(responses)),
        "participants": int(responses["participant_id"].nunique()),
        "complete_participants": int(participant["complete"].sum()),
        "consent_confirmed_responses": int(responses["consent_confirmed"].sum()),
        "missing_required_values": missing_required,
        "duplicate_participant_cases": duplicates,
        "participant_groups": responses.groupby("participant_group")["participant_id"].nunique().astype(int).to_dict(),
        "counterbalance_groups": responses.groupby("counterbalance_group")["participant_id"].nunique().astype(int).to_dict(),
        "condition_trials": responses["condition"].value_counts().astype(int).to_dict(),
        "earlier_collection_participants": int(participant["earlier_collection_date_flag"].sum()),
        "median_recorded_total_seconds": float(participant["recorded_total_seconds"].median()),
        "participants_under_120_seconds": int((participant["recorded_total_seconds"] < 120).sum()),
        "largest_identical_response_vector": int(repeated.max()),
        "comments_present": int(responses["comments"].fillna("").str.strip().ne("").sum()),
        "bootstrap_seed": args.seed,
        "bootstrap_iterations": args.bootstrap,
        "analysis_status": "complete_after_verified_participant_group_correction",
    }
    (args.output / "DATA_AUDIT.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    write_markdown(args.output / "PROTOCOL_DEVIATIONS.md", audit, condition_summary)

    results = {
        "audit": audit,
        "incorrect_recommendation": {
            row["measure"]: row["value"] for row in incorrect_summary.to_dict("records")
        },
        "condition_metrics": ci_frame.to_dict("records"),
        "planned_contrasts": pd.read_csv(args.output / "planned_condition_contrasts.csv").to_dict("records"),
    }
    (args.output / "human_study_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    workbook_payload = {
        "audit": audit,
        "condition_exposure": condition_summary.to_dict("records"),
        "condition_metrics": ci_frame.to_dict("records"),
        "planned_contrasts": pd.read_csv(
            args.output / "planned_condition_contrasts.csv"
        ).to_dict("records"),
        "incorrect_recommendation": incorrect_summary.to_dict("records"),
        "decision_distribution": decision_distribution.to_dict("records"),
        "participant_audit": json.loads(
            participant.to_json(orient="records", date_format="iso")
        ),
        "analysis_ready_responses": json.loads(
            responses[public_columns].to_json(orient="records", date_format="iso")
        ),
    }
    (args.output / "workbook_payload.json").write_text(
        json.dumps(workbook_payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
