# Independent Review Instructions

## Safeguards

The safeguard and action-set files follow the supervisor- and university-approved structured review protocol. Do not replace the protocol provenance with a person's name unless that person actually reviewed the records.

## Reference action sets

Review at least 30 cases in `acceptable_action_set_review.csv`. Use only Increase, Maintain, Reduce and Investigate. Record acceptable, conditionally acceptable and unacceptable actions as semicolon-separated sets. Explain the conditions and disagreements. Do not overwrite the original primary reference action.

## Safeguard interventions

Rows marked `Candidate_Safe_Intervention=Yes` in `safeguard_intervention_audit.csv` use the frozen action-set criterion: the unconstrained action must be unacceptable, and the constrained outcome must be acceptable or conditional. A No Safe Recommendation is correct only when Increase, Maintain and Reduce are all unacceptable and Investigate remains an acceptable manual fallback. Exact primary-label agreement is reported separately.

The current diagnostic run may contain fewer than 10 candidates. If so, create the remaining cases in `additional_intervention_case_review.csv` from genuine or expert-approved scenarios. Record the source and case facts. Do not duplicate one case under multiple seeds or invent a favourable label after viewing the model output.
