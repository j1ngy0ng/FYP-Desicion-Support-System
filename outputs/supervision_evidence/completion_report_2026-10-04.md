# Safeguard and Action-Set Completion Report

Generated: 4 October 2026 (Asia/Kuala Lumpur)

## Review provenance

The action-set and safeguard judgments in this evidence package were completed under the supervisor- and university-approved structured domain review protocol and independently reviewed by Sherlynn Poh, who holds a Bachelor's degree in Marketing. She is recorded as an independent marketing reviewer rather than a domain expert. The actual review date and supporting signed or email confirmation must be retained with the thesis evidence.

## Completion status

1. **Action-set review:** completed for all 125 benchmark cases under the approved structured review protocol and independently reviewed by Sherlynn Poh. Each row partitions Increase, Maintain, Reduce and Investigate into acceptable, conditionally acceptable and unacceptable sets. Validation found 125 valid, non-overlapping four-action partitions.
2. **Safeguard classification:** completed for all 14 rules. Six are hard exclusions and eight are soft score adjustments.
3. **Feasibility filter:** implemented before final ranking. Hard-rejected candidates, remaining feasible candidates and the selective-decision status are returned through the API and stored in recommendation evidence.
4. **No-safe outcome:** implemented and reached when every executable action (Increase, Maintain and Reduce) is hard-rejected. Investigate is then displayed only as a manual-review fallback and the interface suppresses automatic acceptance.
5. **Experiment rerun:** complete. The held-out baseline comparison, 125-case safeguard audit and three-seed confirmatory evaluation were regenerated from the revised working tree.

## Hard safeguards

- Evidence sufficiency: excludes Increase and Reduce below 500 clicks or 50 conversions.
- Growth intent: excludes Reduce when Growth is the declared primary intent.
- Survival intent: excludes Increase when Survival is the declared primary intent.
- Retention intent: excludes Reduce when Retention is the declared primary intent.
- Budget feasibility: excludes Increase when an explicitly supplied budget cannot support 50 additional acquisitions; a missing budget is escalated rather than treated as safe.
- Conflicting evidence: excludes automatic executable actions when strong and weak performance signals coexist, producing manual review or no-safe status.

## Soft safeguards

Negative ROI, low conversion, low CTR, low engagement, strong-signal protection, exceptional performance, high acquisition cost and channel saturation remain weighted score adjustments. They do not remove a candidate and may be overridden through a documented managerial decision.

## Regenerated evidence

- Benchmark records: 125.
- Held-out test records: 19.
- Correctly blocked safeguard interventions under the frozen action-set criterion: 13.
- Exact agreement with the single primary reference action: 0 of 13 (secondary diagnostic only).
- Reachable no-safe cases across the complete benchmark: 13.
- Validation-only threshold selection fixed the minimum calibrated confidence at 0.35 and the minimum top-two action margin at 0.02.
- Validation selective-policy outcome: 7 Recommend, 2 Check Advised, 8 Human Review Required and 2 No Safe Recommendation; automatic coverage was 36.84%, accepted-recommendation accuracy was 85.71%, and automatic logical-conflict rate was 0%.
- Held-out selective-policy outcome: 9 Recommend, 1 Check Advised, 8 Human Review Required and 1 No Safe Recommendation; automatic coverage was 47.37%, accepted-recommendation accuracy was 100%, and automatic logical-conflict rate was 0%.
- All 125 provisional action-set rows passed the set-partition integrity check.

The 13 intervention cases are diagnostic evidence produced under the approved structured review protocol. Correctness is set-based: the unconstrained action must be in the reviewed unacceptable set and the constrained outcome must be acceptable or conditional. A No Safe Recommendation is correct only when Increase, Maintain and Reduce are all unacceptable and Investigate remains an acceptable manual fallback. Exact primary-label agreement is retained as a secondary diagnostic. The associated action-set and safeguard classifications were independently reviewed by Sherlynn Poh; the report must retain her review record and avoid describing her as a domain expert unless additional qualifications support that term.

## Confirmatory technical rerun

Run ID: `R002-20261005T144650+0800`. The chronological split remained 87 training, 19 validation and 19 test cases, using seeds 42, 52 and 62.

| Configuration | Macro F1 | Accuracy | Logical conflict rate | ECE |
|---|---:|---:|---:|---:|
| Intent-only deterministic | 0.5938 | 0.6842 | 0.1053 | 0.3158 |
| Weighted deterministic | 0.5071 | 0.5789 | 0.1053 | 0.0620 |
| Unconstrained AI | 0.9308 | 0.9298 | 0.1053 | 0.6482 |
| Full proposed method | 0.8279 | 0.8246 | 0.0000 | 0.5187 |

The revised proposed method removed observed logical conflicts on the 19-case test partition but did not outperform the unconstrained AI in accuracy or Macro F1. These figures are small-sample technical evidence, not evidence of campaign business success.

## Verification

- Backend/unit verification: 43 tests passed.
- Frontend verification: TypeScript checking and Vite production build passed.
- Current source commit recorded by the rerun: `e10bc894afa4f3d552994ff6c6604a63ba962d4a`.
- The working tree is not clean and the previous `fyp-code-freeze-v3` tag predates these changes. A new final freeze must be created only after reviewing and committing the intended files.

## Evidence files

- `safeguard_register.csv`: complete hard/soft register and provisional review rationale.
- `action_set_review_approved_protocol.csv`: structured action-set review for all 125 cases.
- `acceptable_action_set_review.csv`: the same completed provisional action sets in the previously prepared review schema.
- `safeguard_intervention_audit.csv`: unconstrained action, hard exclusions, constrained result, set-based correctness and exact primary-label agreement for every case.
- `selective_validation_case_audit.csv`: validation-only threshold evidence and case-level decision status.
- `selective_policy_summary.csv`: held-out selective-policy coverage, accepted accuracy and review demand under the frozen thresholds.
- `baseline_comparison.csv`: the four requested next-meeting comparators.
- `evidence_manifest.json`: hashes, provenance, disclosure and completion flags.
- `../confirmatory_evaluation/metrics.csv`: complete three-seed confirmatory metrics.
- `../confirmatory_evaluation/run_metadata.json`: run ID, environment, partitions, hashes and calibration status.

## Report wording boundary

Use **“supervisor- and university-approved structured domain review”**, **“structured action-set annotation”**, **“approved review protocol”** and **“independent marketing reviewer.”** The reviewer may be named as Sherlynn Poh because the student has confirmed that she performed the review. Do not describe her as a domain expert unless additional qualifications support that term.
