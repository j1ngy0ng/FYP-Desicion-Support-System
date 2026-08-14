# Chapter 4 verification manifest — 14 August 2026

This manifest supports the Chapter 4 as-built statements. Performance results remain Chapter 5 evidence.

## Source-freeze boundary

- The implementation is frozen by the annotated Git tag `fyp-code-freeze-v1` before the confirmatory rerun.
- The exact source commit and tag are recorded by `outputs/confirmatory_evaluation/run_metadata.json` when the frozen runner executes.
- Temporary document-rendering material and superseded figure variants were moved to `C:\Users\user\Desktop\FYP Repository Archive\strict-review-20260814` rather than committed.

## Data and configuration

| Artefact | Shape / identifier | SHA-256 |
|---|---:|---|
| `data/layers/01_raw_dataset_55555x16.csv` | 55,555 records × 16 fields | `4969A1C5961FBA85772822467F87E2C3069107017BDC6D685C21B47A0ED22665` |
| `data/layers/02_processed_model_data.csv` | 55,555 records × 31 fields | `7979E95284E034236E684DE0E26E00D551BA7BA0DBABE3F2A5A71655E212B1DD` |
| `data/benchmark_audited.csv` | 125 records × 26 fields | `3F2320FBD190B24766DB4453AB1DC7E7B212803FDFA2AC048C2437012D4D51EE` |
| `data/rule_catalogue_v1.json` | `rule-catalogue-v1`; 14 predefined rules | `C048D442C121C7B4820DBD0271B8133B9B75D0B9CCB436B5C1D6317C8FDD2F7A` |

Chronological partition membership is:

- campaign data: 38,888 training; 8,333 validation; 8,334 test;
- audited benchmark: 87 training; 19 validation; 19 test;
- the calibration eligibility gate is `|B| ≥ 120` on the complete audited benchmark, not on the 19-case validation subset.

## Implemented controls

- Training-partition medians, scalers, ROI clipping/target statistics, model parameters and channel evidence are fitted from training data only.
- The 19 audited validation cases fit only temperature scaling from locked score vectors and audited operational reference actions.
- Held-out test cases are excluded from fitting, calibration, rule revision and explanation-template revision.
- An omitted budget remains `null`; the budget-feasibility rule is skipped without evidence. Explicit zero and positive budgets are evaluated as real values.
- `action_evidence_status` records `audited_actionnet`, `development_actionnet` or `campaignnet_only_fallback`. The fallback also adds a user-visible caveat.
- The 14 rule weights and priorities are predefined and frozen; training and validation do not learn them.
- Human-study endpoints are locked unless `ETHICS_APPROVAL_REFERENCE` contains a formal TAR UMT approval or exemption reference.

## Verification commands

```text
.venv\Scripts\python -m unittest backend.tests.test_engine backend.tests.test_api tests.test_three_layer_data tests.test_human_provided_dataset tests.test_baseline_evaluation
pnpm build
```

The verified suite contains 36 tests after adding the ethics, budget and ActionNet trace cases. The frontend command performs TypeScript checking and a Vite production build. Docker is not installed in the captured Windows environment, so no executed MySQL 8.4 integration run is claimed; API verification uses a freshly recreated SQLite prototype through the same SQLAlchemy models.

## Editable figures

Final editable Draw.io sources and matching PNG exports for the revised Chapter 4 figures are retained in `docs/chapter4_figures/`. Superseded duplicate variants are archived outside the repository.
