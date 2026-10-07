# Next Supervision Evidence Status

Generated on 2026-10-07T13:20:10+08:00 from the current working tree.

## Scope decision requiring supervisor confirmation

The implemented system recommends one campaign investment action: Increase, Maintain, Reduce or Investigate. It does not select a marketing channel as its primary output. Channel history is supporting campaign-level evidence. This narrower action unit is internally consistent with the current code and benchmark but differs from the channel-first example in the supervisor analysis. Confirm this scope before final evaluation.

## Completed repository evidence

- Three declared intents are locked: Survival, Retention and Growth. The user supplies one primary intent; mixed intent is outside the current study scope.
- The benchmark contains 125 audited cases. Intent distribution: {'Survival': 34, 'Retention': 55, 'Growth': 36}. Action distribution: {'Reduce': 34, 'Maintain': 48, 'Investigate': 25, 'Increase': 18}.
- The requested intent-only deterministic, weighted deterministic and unconstrained AI comparators are included in `baseline_comparison.csv` on the locked 19-case chronological test partition.
- The proposed method exposes RECOMMEND, CHECK ADVISED, HUMAN REVIEW REQUIRED and a reachable NO SAFE RECOMMENDATION state.
- `selective_policy_summary.csv` reports automatic coverage, accepted-action accuracy, review demand, unresolved rate and automatic conflict rate on the held-out test partition.
- The all-case diagnostic audit found 13 correctly blocked interventions under the frozen action-set criterion and 13 no-safe outcomes. Exact primary-label agreement is retained as a secondary diagnostic and is 0 of 13 interventions.

## Approved structured domain review

- `safeguard_register.csv` records 6 hard and 8 soft safeguards with explicit rationales.
- `acceptable_action_set_review.csv` and `action_set_review_approved_protocol.csv` contain provisional action sets for all 125 cases.
- These records follow the supervisor- and university-approved structured review protocol and were independently reviewed by Sherlynn Poh, who holds a Bachelor's degree in Marketing.

## External evidence still required

- Retain Sherlynn Poh's dated signature or email confirmation with the thesis evidence.
- Formal TAR UMT ethics approval is documented by the Ethics Committee Checklist retained outside the public repository. The approved local study deployment supplies this document title through `ETHICS_APPROVAL_REFERENCE`.
- The current 125-case source lacks business size, business maturity, available budget, operational constraints and prohibited-action fields. These gaps require either source enrichment or an explicit study-scope limitation.

## Claim boundary

The generated baseline table is technical evidence for the held-out benchmark. The intervention audit across all 125 cases is a diagnostic review set, not an unbiased performance result. No claim of SME revenue, retention, growth or real campaign success is supported.
