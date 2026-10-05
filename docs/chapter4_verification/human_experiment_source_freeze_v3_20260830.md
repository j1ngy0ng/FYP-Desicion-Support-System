# Human Experiment Source Freeze v3

Freeze purpose: experiment-ready system version before participant study.

Freeze timestamp: 2026-08-30T20:16:58.9921234+08:00

Git branch: main

Git commit: e10bc894afa4f3d552994ff6c6604a63ba962d4a

Git tag: fyp-code-freeze-v3

Commit message: Freeze experiment-ready system version

Verification performed before tagging:

- Backend/API/system tests: `.venv\Scripts\python -m unittest backend.tests.test_engine backend.tests.test_api tests.test_three_layer_data tests.test_human_provided_dataset tests.test_baseline_evaluation`
- Test result: 39 tests passed
- Frontend build: `npx pnpm build`
- Build result: passed

Environment snapshot:

- Python: 3.11.9
- Node.js: v24.18.0
- pnpm: 11.16.0

Data and rule hashes:

- `data/benchmark_audited.csv`: SHA256 `3F2320FBD190B24766DB4453AB1DC7E7B212803FDFA2AC048C2437012D4D51EE`
- `data/rule_catalogue_v1.json`: SHA256 `C048D442C121C7B4820DBD0271B8133B9B75D0B9CCB436B5C1D6317C8FDD2F7A`
- `data/layers/01_raw_dataset_55555x16.csv`: SHA256 `4969A1C5961FBA85772822467F87E2C3069107017BDC6D685C21B47A0ED22665`

Scope note:

- The tag freezes the current executable system source for the human experiment.
- Uncommitted report drafts, exported review documents and alternative figure drafts remain in the working directory but are not part of the frozen source tag.
- Do not change backend logic, frontend study labels, recommendation logic, rule catalogue, benchmark data or calibration settings after participant recruitment starts. If any of these change, create a new freeze tag and restart the affected experiment evidence.
