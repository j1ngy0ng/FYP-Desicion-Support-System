# FYP-Desicion-Support-System
Intent-Aware Logic-Constrained Neuro-Symbolic Decision Support System with Trust Calibration for SME Multi-Channel Marketing

## Baseline evaluation (Chapter 3)

Run the baseline systems and generate comparison-table-ready metrics:

```bash
python baseline_evaluation.py
```

Run stress evaluation with a separate conflict-focused dataset (original dataset remains unchanged):

```bash
python baseline_evaluation.py --dataset data/Dataset_conflict_stress.csv --output-dir outputs/conflict_stress
```

The standard holdout can legitimately report a `0.0000` logical conflict rate when none of
the baseline recommendations violate the configured conflict rules. Use the conflict-stress
dataset to verify that the metric detects contradictory recommendations; a non-zero value is
not manufactured for the standard dataset.

Generated outputs:

- `outputs/normal/` contains the normal-dataset results.
- `outputs/conflict_stress/` contains the robustness-test results.

Logical Conflict Rate uses the predefined, system-independent catalogue in
[`docs/CONFLICT_RULES.md`](docs/CONFLICT_RULES.md). Prediction outputs include a conflict flag and
the exact rule identifiers triggered for each baseline recommendation.

## Project structure

- `data/`: normal and conflict-stress datasets.
- `docs/`: FYP report and logical-conflict rule catalogue.
- `tests/`: automated evaluation-rule tests.
- `outputs/`: generated results separated by experiment.
- `system_components/`: Chapter 4 implementation scaffold grouped into five architectural layers.

## User-interface prototype

Run the Chapter 4 web interface locally:

```bash
python -m http.server 8000 --directory system_components/presentation_layer/web_app
```

Open `http://127.0.0.1:8000`. The prototype includes all eleven report interfaces and
uses in-memory demonstration data; backend persistence and recommendation algorithms are
separate implementation tasks.
