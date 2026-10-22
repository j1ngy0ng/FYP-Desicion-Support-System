#!/usr/bin/env python3
"""Write the immutable evidence manifest for the supplemental action-set study."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path


BASE = Path("outputs/additional_test_review_20261022")
FILES = (
    "additional_heldout_cases.csv",
    "selection_manifest.json",
    "reviewer_1_sherlynn_raw.xlsx",
    "reviewer_2_raw.xlsx",
    "reviewer_agreement_summary.json",
    "reviewer_disagreements.csv",
    "acceptable_action_set_adjudication_completed_raw.xlsx",
    "acceptable_action_sets_frozen.csv",
    "acceptable_action_sets_frozen.json",
    "supplemental_evaluation/metrics.csv",
    "supplemental_evaluation/seed_metrics.csv",
    "supplemental_evaluation/predictions.csv",
    "supplemental_evaluation/per_intent_metrics.csv",
    "supplemental_evaluation/decision_statuses.csv",
    "supplemental_evaluation/reliability_seed42.csv",
    "supplemental_evaluation/confidence_intervals.json",
    "supplemental_evaluation/selective_policy_summary.json",
    "supplemental_evaluation/run_metadata.json",
    "SUPPLEMENTAL_VERIFICATION_SUMMARY.md",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> None:
    missing = [str(BASE / relative) for relative in FILES if not (BASE / relative).is_file()]
    if missing:
        raise FileNotFoundError("Missing evidence files: " + ", ".join(missing))
    manifest = {
        "status": "FROZEN_POST_CONFIRMATORY_SUPPLEMENTAL_EVIDENCE",
        "frozen_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cases": 50,
        "review_protocol": {
            "reviewers": 2,
            "reviewer_1": "Sherlynn Poh; Bachelor in Marketing (qualification confirmed by the student)",
            "reviewer_2": "Identity recorded as anonymous; workbook records Bachelor in Marketing",
            "direct_agreement_cases": 14,
            "adjudicated_cases": 36,
            "adjudicator": "Sherlynn Poh",
            "adjudication_date": "2026-10-22",
            "model_output_blinding": "Model outputs were generated after the final action-set file was frozen.",
        },
        "evaluation_boundary": {
            "type": "same-source post-confirmatory held-out robustness evaluation",
            "not_external_validation": True,
            "does_not_replace_original_19_case_confirmatory_test": True,
            "model_fit_overlap": 0,
            "primary_endpoint": "Admissible Set Accuracy, where Acceptable and Conditional actions count as admissible",
        },
        "files": {
            relative: {
                "sha256": sha256(BASE / relative),
                "bytes": (BASE / relative).stat().st_size,
            }
            for relative in FILES
        },
    }
    path = BASE / "supplemental_evidence_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(path), "sha256": sha256(path), "files": len(FILES)}, indent=2))


if __name__ == "__main__":
    main()
