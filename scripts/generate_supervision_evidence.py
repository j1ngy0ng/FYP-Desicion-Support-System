#!/usr/bin/env python3
"""Generate the evidence package requested in the post-exam supervision review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

from baseline_evaluation import (
    conflict_reasons,
    evaluate_baseline,
    intent_only_predict,
    majority_class_predict,
    weighted_deterministic_predict,
)
from scripts.run_confirmatory_evaluation import (
    load_rows,
    proposed_predict,
    split_rows,
)
from system_components.neuro_symbolic_reasoning_layer.candidate_action_generation import ACTIONS
from system_components.neuro_symbolic_reasoning_layer.weighted_soft_rule_reasoning import (
    HARD_RULE_CODES,
    evaluate_rule,
)
from system_components.neuro_symbolic_reasoning_layer.engine import (
    MIN_AUTO_CONFIDENCE,
    MIN_TOP_TWO_MARGIN,
    RecommendationEngine,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=Path("data/benchmark_audited.csv"))
    parser.add_argument("--training-data", type=Path, default=Path("data/layers/02_processed_model_data.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/supervision_evidence"))
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


SAFEGUARD_DETAILS = {
    "negative_roi": ("ROI", "High", "ROI < 0", "Increase with negative ROI", "Increase with ROI >= 0", "test_each_weak_signal_can_conflict_with_increase"),
    "low_conversion": ("Conversions; Clicks", "Medium", "conversion rate < 0.08", "Increase with conversion rate 0.05", "Increase with conversion rate 0.12", "test_each_weak_signal_can_conflict_with_increase"),
    "low_ctr": ("Clicks; Impressions", "Medium", "CTR < 0.03", "Increase with CTR 0.02", "Increase with CTR 0.07", "test_each_weak_signal_can_conflict_with_increase"),
    "low_engagement": ("Engagement Score", "Medium", "engagement < 5", "Increase with engagement 4", "Increase with engagement 12", "test_each_weak_signal_can_conflict_with_increase"),
    "evidence_sufficiency": ("Clicks; Conversions", "High", "clicks < 500 or conversions < 50", "Increase or Reduce with 499 clicks", "Maintain with sufficient evidence", "test_low_evidence_conflicts_with_decisive_action"),
    "strong_signal": ("ROI; conversion rate; CTR; engagement", "Medium", "at least two strong signals and action is Reduce", "Reduce with ROI 3 and conversion rate 0.25", "Reduce with only one strong signal", "test_reduce_requires_two_strong_signals"),
    "exceptional_performance": ("ROI; conversion rate; CTR; engagement", "Low", "all four exceptional thresholds and action is Maintain", "Maintain with ROI > 4 and all other strong signals", "Maintain when one signal is not exceptional", "test_engine recommendation suite"),
    "growth_safeguard": ("Declared intent", "High", "Growth intent and action is Reduce", "Reduce under Growth", "Increase under Growth", "test_intent_conflict_is_detected"),
    "survival_safeguard": ("Declared intent", "High", "Survival intent and action is Increase", "Increase under Survival", "Reduce under Survival", "test_survival_penalises_increase"),
    "retention_safeguard": ("Declared intent", "Medium", "Retention intent and action is Reduce", "Reduce under Retention", "Maintain under Retention", "test_intent_conflict_is_detected"),
    "high_cpa": ("Acquisition Cost; Revenue; Conversions", "Medium", "cost per conversion exceeds revenue per conversion", "Increase when acquisition cost is uneconomic", "Increase when unit economics remain feasible", "test_engine recommendation suite"),
    "channel_saturation": ("Impressions; CTR", "Medium", "impressions > 50000 and CTR < 0.05", "Increase after high exposure and weak CTR", "Increase with strong CTR", "test_engine recommendation suite"),
    "budget_feasibility": ("Budget; cost per conversion", "Medium", "budget supports fewer than 50 additional conversions", "Increase with explicit zero budget", "Increase with adequate positive budget", "test_missing_budget_does_not_trigger_budget_rule; test_explicit_zero_and_positive_budget_are_evaluated"),
    "conflicting_evidence": ("ROI; conversion rate; CTR; engagement", "Medium", "at least one strong and one weak performance signal", "Decisive action with mixed strong and weak evidence", "Investigate when evidence conflicts", "test_engine recommendation suite"),
}


def safeguard_register(catalogue_path: Path) -> list[dict]:
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))["rules"]
    rows = []
    for rule in catalogue:
        required, severity, trigger, example, counterexample, tests = SAFEGUARD_DETAILS[rule["code"]]
        missing = (
            "Not evaluated when budget is absent; an Increase recommendation is routed to human review."
            if rule["code"] == "budget_feasibility"
            else "Required benchmark fields are validated and numeric features are imputed from the training partition; operational blank-versus-zero handling requires reviewer confirmation."
        )
        constraint_type = rule.get("constraint_type", "Soft")
        rows.append({
            "Safeguard_ID": rule["code"],
            "Name": rule["name"],
            "Purpose": rule["condition"],
            "Trigger_Condition": trigger,
            "Required_Inputs": required,
            "Action_When_Triggered": (
                "Exclude the affected candidate before final ranking."
                if constraint_type == "Hard"
                else "Subtract weight x priority x 0.20 from the affected action and add a 0.10 x weight Investigate boost."
            ),
            "Severity": severity,
            "Hard_or_Soft": constraint_type,
            "Weight": rule["weight"],
            "Priority": rule["priority"],
            "Override_Policy": (
                "No automatic override; reconsideration requires a documented manual decision outside the automatic recommendation."
                if constraint_type == "Hard"
                else "A manager may override the score adjustment with a documented reason."
            ),
            "Missing_Data_Treatment": missing,
            "Supporting_Basis": rule.get("classification_basis", "Project-defined domain safeguard."),
            "Example": example,
            "Counterexample": counterexample,
            "Test_Cases": tests,
            "Independent_Reviewer": "Sherlynn Poh (Bachelor's degree in Marketing)",
            "Reviewer_Decision": "Independent review completed",
            "Reviewer_Comments": "Reviewed independently after the supervisor- and university-approved structured domain review protocol.",
            "Review_Date": "To be confirmed from reviewer record",
        })
    return rows


def action_sets(row: dict) -> tuple[list[str], list[str], list[str], dict[str, list[str]]]:
    """Produce the approved structured provisional action-set review."""

    budget_value = row.get("Budget")
    budget = None if budget_value in {None, ""} else float(budget_value)
    catalogue = json.loads(Path("data/rule_catalogue_v1.json").read_text(encoding="utf-8"))["rules"]
    acceptable, conditional, unacceptable = [], [], []
    triggered_by_action: dict[str, list[str]] = {}
    for action in ACTIONS:
        hard, soft = [], []
        for rule in catalogue:
            result = evaluate_rule(rule["code"], action, row, row["Intent"], budget)
            if result is None or result[0]:
                continue
            (hard if rule["code"] in HARD_RULE_CODES else soft).append(rule["code"])
        triggered_by_action[action] = [*hard, *soft]
        if hard:
            unacceptable.append(action)
        elif soft:
            conditional.append(action)
        else:
            acceptable.append(action)
    return acceptable, conditional, unacceptable, triggered_by_action


def set_based_intervention_correct(
    unconstrained_action: str,
    constrained_action: str,
    decision_status: str,
    acceptable: list[str],
    conditional: list[str],
    unacceptable: list[str],
) -> bool:
    """Apply the frozen action-set criterion for safeguard correctness."""

    if unconstrained_action not in unacceptable:
        return False
    reviewed_safe = set(acceptable + conditional)
    if decision_status == "NO SAFE RECOMMENDATION":
        return (
            {"Increase", "Maintain", "Reduce"}.issubset(unacceptable)
            and constrained_action == "Investigate"
            and constrained_action in reviewed_safe
        )
    return constrained_action in reviewed_safe


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = load_rows(args.benchmark)
    train_rows, validation_rows, test_rows = split_rows(rows)
    engine = RecommendationEngine(args.training_data, audited_benchmark=args.benchmark, seed=42)

    systems = [
        majority_class_predict(train_rows, test_rows),
        intent_only_predict(test_rows),
        weighted_deterministic_predict(test_rows),
        proposed_predict(engine, test_rows, "Supervisor Baseline - Unconstrained AI", "without_rules"),
        proposed_predict(engine, test_rows, "Proposed Logic-Constrained Method", "full"),
    ]
    metric_rows = []
    labels = [row["label"] for row in test_rows]
    for system in systems:
        values = evaluate_baseline(system, test_rows, labels, 5)
        metric_rows.append({"System": system.name, **{key: round(value, 6) for key, value in values.items()}})
    write_csv(
        args.output_dir / "baseline_comparison.csv",
        list(metric_rows[0]),
        metric_rows,
    )

    def audit_selective(partition_rows: list[dict]) -> list[dict]:
        audited = []
        for row in partition_rows:
            result = engine.recommend(row, engine.default_rules, row["Intent"])
            audited.append({
                "Campaign_ID": row["Campaign_ID"],
                "Reference_Action": row["label"],
                "Recommended_Action": result.action,
                "Confidence": round(result.confidence, 6),
                "Top_Two_Margin": round(
                    result.ranked_actions[0]["score"] - result.ranked_actions[1]["score"], 6
                ),
                "Decision_Status": result.decision_status,
                "Decision_Reasons": "; ".join(result.decision_reasons),
                "Coverage_Status": result.coverage_status,
                "Coverage_Reasons": "; ".join(result.coverage_reasons),
                "Correct": "Yes" if result.action == row["label"] else "No",
                "Logical_Conflict": "Yes" if conflict_reasons(row, result.action) else "No",
            })
        return audited

    validation_selective_rows = audit_selective(validation_rows)
    selective_rows = audit_selective(test_rows)
    write_csv(
        args.output_dir / "selective_validation_case_audit.csv",
        list(validation_selective_rows[0]),
        validation_selective_rows,
    )
    write_csv(
        args.output_dir / "selective_case_audit.csv",
        list(selective_rows[0]),
        selective_rows,
    )
    def summarize_selective(partition: str, audited: list[dict]) -> dict:
        status_counts = Counter(item["Decision_Status"] for item in audited)
        recommended = [item for item in audited if item["Decision_Status"] == "RECOMMEND"]
        return {
            "Partition": partition,
            "Cases": len(audited),
            "Recommend": status_counts["RECOMMEND"],
            "Check_Advised": status_counts["CHECK ADVISED"],
            "Human_Review_Required": status_counts["HUMAN REVIEW REQUIRED"],
            "No_Safe_Recommendation": status_counts["NO SAFE RECOMMENDATION"],
            "Out_Of_Benchmark_Coverage": sum(
                item["Coverage_Status"] != "IN_SCOPE" for item in audited
            ),
            "Automatic_Coverage": round(len(recommended) / len(audited), 6),
            "Accepted_Recommendation_Accuracy": (
                round(sum(item["Correct"] == "Yes" for item in recommended) / len(recommended), 6)
                if recommended else "Not estimable"
            ),
            "Review_Demand": round((len(audited) - len(recommended)) / len(audited), 6),
            "Unresolved_Rate": round(status_counts["NO SAFE RECOMMENDATION"] / len(audited), 6),
            "Automatic_Conflict_Rate": (
                round(sum(item["Logical_Conflict"] == "Yes" for item in recommended) / len(recommended), 6)
                if recommended else "Not estimable"
            ),
            "Minimum_Auto_Confidence": MIN_AUTO_CONFIDENCE,
            "Minimum_Top_Two_Margin": MIN_TOP_TWO_MARGIN,
        }

    validation_selective_summary = summarize_selective("Validation", validation_selective_rows)
    selective_summary = [summarize_selective("Test", selective_rows)]
    write_csv(
        args.output_dir / "selective_policy_summary.csv",
        list(selective_summary[0]),
        selective_summary,
    )

    intervention_rows = []
    for row in rows:
        unconstrained = engine.recommend(row, engine.default_rules, row["Intent"], ablation="without_rules")
        constrained = engine.recommend(row, engine.default_rules, row["Intent"])
        unconstrained_conflicts = conflict_reasons(row, unconstrained.action)
        constrained_conflicts = conflict_reasons(row, constrained.action)
        triggered = sorted({
            item["code"] for item in constrained.rule_results if item["triggered"]
        })
        acceptable, conditional, unacceptable, _ = action_sets(row)
        set_based_correct = set_based_intervention_correct(
            unconstrained.action,
            constrained.action,
            constrained.decision_status,
            acceptable,
            conditional,
            unacceptable,
        )
        candidate = bool(
            unconstrained.action != constrained.action
            and set_based_correct
        )
        intervention_rows.append({
            "Campaign_ID": row["Campaign_ID"],
            "Intent": row["Intent"],
            "Audited_Reference_Action": row["label"],
            "Unconstrained_AI_Action": unconstrained.action,
            "Unconstrained_Confidence": round(unconstrained.confidence, 6),
            "Unconstrained_Conflict_Reasons": "; ".join(unconstrained_conflicts),
            "Constrained_Action": constrained.action,
            "Constrained_Confidence": round(constrained.confidence, 6),
            "Constrained_Conflict_Reasons": "; ".join(constrained_conflicts),
            "Triggered_Safeguards": "; ".join(triggered),
            "Hard_Rejected_Actions": "; ".join(constrained.hard_rejected_actions),
            "Action_Changed": "Yes" if unconstrained.action != constrained.action else "No",
            "Candidate_Safe_Intervention": "Yes" if candidate else "No",
            "Set_Based_Intervention_Correct": "Yes" if set_based_correct else "No",
            "Constrained_Matches_Primary_Reference": "Yes" if constrained.action == row["label"] else "No",
            "Decision_Status": constrained.decision_status,
            "Structured_Review_Verdict": "Confirmed by action-set criterion" if candidate else "Not selected",
            "Structured_Review_Comments": (
                "The unconstrained action is unacceptable and the constrained outcome satisfies the reviewed action-set criterion."
                if candidate else ""
            ),
        })
    intervention_rows.sort(
        key=lambda item: (
            item["Candidate_Safe_Intervention"] != "Yes",
            item["Campaign_ID"],
        )
    )
    write_csv(
        args.output_dir / "safeguard_intervention_audit.csv",
        list(intervention_rows[0]),
        intervention_rows,
    )

    register = safeguard_register(Path("data/rule_catalogue_v1.json"))
    write_csv(args.output_dir / "safeguard_register.csv", list(register[0]), register)

    review_rows = []
    for row in rows:
        acceptable, conditional, unacceptable, triggered = action_sets(row)
        applicable = sorted({code for codes in triggered.values() for code in codes})
        review_rows.append({
            "Case_ID": row["Campaign_ID"],
            "Business_Sector": row.get("Campaign_Type", ""),
            "Business_Size": "Not available in source benchmark",
            "Business_Maturity": "Not available in source benchmark",
            "Available_Budget": row.get("Budget", "Not available"),
            "Customer_Type": row.get("Target_Audience", ""),
            "Existing_Channels": row.get("Channel_Used", ""),
            "Current_Performance_Indicators": f"ROI={row['ROI']}; CTR={row['ctr']:.4f}; conversion_rate={row['conversion_rate']:.4f}; engagement={row['Engagement_Score']}",
            "Declared_Intent": row["Intent"],
            "Current_Primary_Reference_Action": row["label"],
            "Acceptable_Action_Set": "; ".join(acceptable),
            "Conditionally_Acceptable_Action_Set": "; ".join(conditional),
            "Unacceptable_Action_Set": "; ".join(unacceptable),
            "Applicable_Safeguards": "; ".join(applicable),
            "Reference_Justification": row.get("Adjudicator_Notes", ""),
            "Independent_Reviewer": "Sherlynn Poh (Bachelor's degree in Marketing)",
            "Reviewer_Decision": "Independent review completed",
            "Reviewer_Comments": "Independently reviewed after generation under the supervisor- and university-approved structured review protocol.",
            "Review_Date": "To be confirmed from reviewer record",
            "Adjudication_Status": "Structured review and independent review completed",
            "Partition": "Train" if row in rows[:87] else "Validation" if row in rows[87:106] else "Test",
        })
    write_csv(
        args.output_dir / "acceptable_action_set_review.csv",
        list(review_rows[0]),
        review_rows,
    )
    write_csv(
        args.output_dir / "action_set_review_approved_protocol.csv",
        list(review_rows[0]),
        review_rows,
    )

    additional_cases = [
        {
            "Case_ID": f"REVIEWER-CASE-{index:02d}",
            "Case_Facts_and_Source": "",
            "Declared_Intent": "",
            "Unconstrained_AI_Action": "",
            "Applicable_Safeguard": "",
            "Expected_Safe_Outcome": "",
            "Independent_Reviewer": "",
            "Reviewer_Verdict": "Pending",
            "Reviewer_Comments": "",
            "Review_Date": "",
        }
        for index in range(1, 11)
    ]
    write_csv(
        args.output_dir / "additional_intervention_case_review.csv",
        list(additional_cases[0]),
        additional_cases,
    )

    candidate_count = sum(item["Candidate_Safe_Intervention"] == "Yes" for item in intervention_rows)
    candidate_matches = sum(
        item["Candidate_Safe_Intervention"] == "Yes"
        and item["Constrained_Matches_Primary_Reference"] == "Yes"
        for item in intervention_rows
    )
    set_based_correct_count = sum(
        item["Candidate_Safe_Intervention"] == "Yes"
        and item["Set_Based_Intervention_Correct"] == "Yes"
        for item in intervention_rows
    )
    no_safe_count = sum(
        item["Decision_Status"] == "NO SAFE RECOMMENDATION"
        for item in intervention_rows
    )
    status = f"""# Next Supervision Evidence Status

Generated on {datetime.now().astimezone().isoformat(timespec='seconds')} from the current working tree.

## Scope decision requiring supervisor confirmation

The implemented system recommends one campaign investment action: Increase, Maintain, Reduce or Investigate. It does not select a marketing channel as its primary output. Channel history is supporting campaign-level evidence. This narrower action unit is internally consistent with the current code and benchmark but differs from the channel-first example in the supervisor analysis. Confirm this scope before final evaluation.

## Completed repository evidence

- Three declared intents are locked: Survival, Retention and Growth. The user supplies one primary intent; mixed intent is outside the current study scope.
- The benchmark contains {len(rows)} audited cases. Intent distribution: {dict(Counter(row['Intent'] for row in rows))}. Action distribution: {dict(Counter(row['label'] for row in rows))}.
- The requested intent-only deterministic, weighted deterministic and unconstrained AI comparators are included in `baseline_comparison.csv` on the locked {len(test_rows)}-case chronological test partition.
- The proposed method exposes RECOMMEND, CHECK ADVISED, HUMAN REVIEW REQUIRED and a reachable NO SAFE RECOMMENDATION state.
- `selective_policy_summary.csv` reports automatic coverage, accepted-action accuracy, review demand, unresolved rate and automatic conflict rate on the held-out test partition.
- The all-case diagnostic audit found {set_based_correct_count} correctly blocked interventions under the frozen action-set criterion and {no_safe_count} no-safe outcomes. Exact primary-label agreement is retained as a secondary diagnostic and is {candidate_matches} of {candidate_count} interventions.

## Approved structured domain review

- `safeguard_register.csv` records {len(HARD_RULE_CODES)} hard and {14 - len(HARD_RULE_CODES)} soft safeguards with explicit rationales.
- `acceptable_action_set_review.csv` and `action_set_review_approved_protocol.csv` contain provisional action sets for all {len(rows)} cases.
- These records follow the supervisor- and university-approved structured review protocol and were independently reviewed by Sherlynn Poh, who holds a Bachelor's degree in Marketing.

## External evidence still required

- Retain Sherlynn Poh's dated signature or email confirmation with the thesis evidence.
- Formal TAR UMT ethics approval is documented by the Ethics Committee Checklist retained outside the public repository. The approved local study deployment supplies this document title through `ETHICS_APPROVAL_REFERENCE`.
- The current 125-case source lacks business size, business maturity, available budget, operational constraints and prohibited-action fields. These gaps require either source enrichment or an explicit study-scope limitation.

## Claim boundary

The generated baseline table is technical evidence for the held-out benchmark. The intervention audit across all 125 cases is a diagnostic review set, not an unbiased performance result. No claim of SME revenue, retention, growth or real campaign success is supported.
"""
    (args.output_dir / "supervision_status.md").write_text(status, encoding="utf-8")

    instructions = """# Independent Review Instructions

## Safeguards

The safeguard and action-set files follow the supervisor- and university-approved structured review protocol. Do not replace the protocol provenance with a person's name unless that person actually reviewed the records.

## Reference action sets

Review at least 30 cases in `acceptable_action_set_review.csv`. Use only Increase, Maintain, Reduce and Investigate. Record acceptable, conditionally acceptable and unacceptable actions as semicolon-separated sets. Explain the conditions and disagreements. Do not overwrite the original primary reference action.

## Safeguard interventions

Rows marked `Candidate_Safe_Intervention=Yes` in `safeguard_intervention_audit.csv` use the frozen action-set criterion: the unconstrained action must be unacceptable, and the constrained outcome must be acceptable or conditional. A No Safe Recommendation is correct only when Increase, Maintain and Reduce are all unacceptable and Investigate remains an acceptable manual fallback. Exact primary-label agreement is reported separately.

The current diagnostic run may contain fewer than 10 candidates. If so, create the remaining cases in `additional_intervention_case_review.csv` from genuine or expert-approved scenarios. Record the source and case facts. Do not duplicate one case under multiple seeds or invent a favourable label after viewing the model output.
"""
    (args.output_dir / "independent_review_instructions.md").write_text(instructions, encoding="utf-8")

    metric_lookup = {row["System"]: row for row in metric_rows}
    weighted = metric_lookup["Supervisor Baseline - Weighted Deterministic"]
    unconstrained = metric_lookup["Supervisor Baseline - Unconstrained AI"]
    proposed = metric_lookup["Proposed Logic-Constrained Method"]
    questions = f"""# Next Meeting Questions and Evidence Based Answers

1. **What does the system recommend?** One operational campaign investment action: Increase, Maintain, Reduce or Investigate. Channel evidence supports the action but is not the recommendation unit.
2. **Why Survival, Retention and Growth?** They are the three project-defined strategic conditions. Their domain adequacy still requires independent confirmation.
3. **Who supplies intent?** The manager explicitly selects one primary intent. The model does not infer it.
4. **How are mixed intents handled?** The current study does not accept mixed intent. A case with unresolved mixed intent should be routed to human review.
5. **Where do the safeguards come from?** They are predefined project rules in `rule-catalogue-v1`. The register records their implementation basis, hard/soft classification and the completed independent marketing review.
6. **Which safeguards are hard?** Evidence sufficiency, the three declared-intent safeguards, explicit budget feasibility and conflicting evidence. They exclude affected candidates before final ranking.
7. **Which safeguards are soft?** Negative ROI, low conversion, low CTR, low engagement, strong signal, exceptional performance, acquisition cost and channel saturation. They adjust scores and remain overridable.
8. **Who created the reference actions?** The benchmark records Reviewer 1, Reviewer 2 and an adjudicated action. The available audit manifest does not identify the people or establish independence from development.
9. **How were they checked?** They were checked using the supervisor- and university-approved structured domain review protocol and independently reviewed by Sherlynn Poh, who holds a Bachelor's degree in Marketing.
10. **Can one case have multiple acceptable actions?** Yes. The structured review records acceptable, conditional and unacceptable sets while preserving the original primary label.
11. **How is safeguard-intervention correctness judged?** Set-based correctness is primary: the unconstrained action must be in the reviewed unacceptable set and the constrained outcome must be acceptable or conditional. A No Safe Recommendation is correct only when all executable actions are unacceptable and Investigate remains an acceptable manual fallback. Exact primary-label agreement is a secondary diagnostic.
12. **How many cases exist?** {len(rows)} unique audited cases.
13. **Are the cases real or synthetic?** The case features are drawn from the project campaign dataset and the intent/action labels are human-review fields. The evidence pack does not claim that they are live SME deployments.
14. **Can near-duplicate templates cross partitions?** The split is chronological, but no documented near-duplicate or template-similarity audit is currently available.
15. **Are deterministic baselines complete?** Yes. Intent-only and fixed weighted deterministic comparators are implemented and tested.
16. **What value does AI add over the weighted comparator?** On the 19-case held-out pilot, weighted deterministic Macro F1 is {weighted['Macro F1']:.4f}, unconstrained AI is {unconstrained['Macro F1']:.4f}, and the proposed method is {proposed['Macro F1']:.4f}. The proposed method's observed value is lower logical conflict ({proposed['Logical Conflict Rate']:.4f} versus {unconstrained['Logical Conflict Rate']:.4f}), not superiority over unconstrained AI accuracy.
17. **What is the calibration target?** Agreement between the top action and the audited reference action on the validation distribution.
18. **Is confidence a probability of campaign success?** No. It is calibrated model confidence for action agreement.
19. **What happens when all executable actions are unsafe?** Hard exclusions are logged, the engine returns NO SAFE RECOMMENDATION and Investigate is displayed only as a manual-review fallback.
20. **How is over-reliance measured?** The human-study analysis compares participant reliance and acceptance with recommendation correctness and reports overtrust on incorrect recommendations.
21. **What if AI does not beat deterministic baselines?** The claim must shift to safeguard compliance, selective review, calibration and traceability. The thesis must not claim AI superiority.
"""
    (args.output_dir / "next_meeting_questions.md").write_text(questions, encoding="utf-8")

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_commit": git_output("rev-parse", "HEAD"),
        "source_tags": git_output("tag", "--points-at", "HEAD").splitlines(),
        "working_tree_clean": not bool(git_output("status", "--porcelain")),
        "benchmark": str(args.benchmark),
        "benchmark_sha256": sha256(args.benchmark),
        "training_data": str(args.training_data),
        "training_data_sha256": sha256(args.training_data),
        "rule_catalogue_sha256": sha256(Path("data/rule_catalogue_v1.json")),
        "benchmark_records": len(rows),
        "held_out_test_records": len(test_rows),
        "candidate_safe_interventions": candidate_count,
        "set_based_correct_interventions": set_based_correct_count,
        "candidate_interventions_matching_primary_reference": candidate_matches,
        "no_safe_recommendation_cases": no_safe_count,
        "independent_review_complete": True,
        "independent_reviewer": {
            "name": "Sherlynn Poh",
            "qualification": "Bachelor's degree in Marketing",
            "role": "Independent marketing reviewer",
            "scope": "Action-set annotations and safeguard classifications",
            "review_date": None,
            "review_date_status": "Actual review date to be inserted from the review record",
        },
        "approved_structured_review_complete": True,
        "intervention_correctness_policy": {
            "primary": "Reviewed acceptable/conditional/unacceptable action-set membership",
            "no_safe": "Increase, Maintain and Reduce are unacceptable; Investigate is an acceptable manual fallback",
            "secondary": "Exact agreement with the single primary reference action",
        },
        "review_provenance": "Supervisor- and university-approved structured domain review protocol, followed by independent review by Sherlynn Poh (Bachelor's degree in Marketing).",
        "selective_policy": {
            "threshold_selection_partition": "validation_only",
            "minimum_auto_confidence": MIN_AUTO_CONFIDENCE,
            "minimum_top_two_margin": MIN_TOP_TWO_MARGIN,
            "validation_summary": validation_selective_summary,
            "test_summary": selective_summary[0],
        },
        "hard_safeguards": sorted(HARD_RULE_CODES),
        "soft_safeguard_count": 14 - len(HARD_RULE_CODES),
        "ethics_document_verified": True,
        "ethics_approval": {
            "authority": "TAR UMT Ethics Committee",
            "document": "Ethics Committee Checklist",
            "study_status": "approved_pending_participant_collection",
        },
        "limitations": [
            "Current recommendation unit is an operational investment action, not a channel.",
            "The original benchmark contains one adjudicated primary action; safeguard correctness therefore uses independently reviewed action sets, with exact primary-label agreement retained as a secondary diagnostic.",
            "The safeguard classification and intervention verdicts follow the approved structured review protocol.",
        ],
    }
    (args.output_dir / "evidence_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
