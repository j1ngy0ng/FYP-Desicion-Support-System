# Post Exam Supervision Candidate v4 — superseded historical checkpoint

Date: 2 October 2026

This file records the state on 2 October 2026 and is retained for traceability. Its open gates were subsequently resolved by the `fyp-code-freeze-v4` implementation and the final evidence package; it must not be read as the current system status.

## Implemented changes

- Added the requested intent-only deterministic comparator.
- Added a fixed weighted deterministic comparator using declared intent, fixed performance thresholds, evidence sufficiency and the shared conflict catalogue.
- Retained an unconstrained AI comparator by running the learned engine without weighted safeguards.
- Added the four-state selective-decision policy: RECOMMEND, CHECK ADVISED, HUMAN REVIEW REQUIRED and NO SAFE RECOMMENDATION.
- Persisted the selective status and its reasons in recommendation evidence and displayed them in the recommendation view.
- Added a reproducible generator for the next-supervision evidence package.

## Verification

Commands:

```text
.venv\Scripts\python -m unittest backend.tests.test_engine backend.tests.test_api tests.test_baseline_evaluation tests.test_three_layer_data tests.test_human_provided_dataset
pnpm build
```

Results:

- 42 Python tests passed.
- TypeScript checking and the Vite production build passed.
- Python 3.11.9, Node.js 24.19.0 and pnpm 11.19.0 were used.

## Generated evidence

The files in `outputs/supervision_evidence/` contain:

- a 14-row safeguard register;
- a 125-case acceptable-action-set review form;
- held-out comparison results for intent-only, weighted deterministic, unconstrained AI and the proposed method;
- an all-case safeguard intervention audit;
- a form for additional reviewer-approved intervention cases;
- reviewer instructions; and
- a hash and provenance manifest.

## Historical open gates and later resolution

- The action-level recommendation unit was retained: Increase, Maintain, Reduce or Investigate.
- The catalogue was classified into six hard and eight soft safeguards, and hard candidate exclusion was implemented.
- All 125 cases received non-overlapping reviewed acceptable, conditional and unacceptable action sets.
- Thirteen set-based safeguard interventions were confirmed; exact primary-label agreement remains a secondary diagnostic and is zero of thirteen.
- A reachable NO SAFE RECOMMENDATION state and validation-selected selective policy were implemented and tested.
- Formal ethics documentation remains an external prerequisite for any participant-result claim; it does not alter the completed technical evaluation.
