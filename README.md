# FYP-Desicion-Support-System
Intent-Aware Logic-Constrained Neuro-Symbolic Decision Support System with Trust Calibration for SME Multi-Channel Marketing

## Baseline evaluation (Chapter 3)

Run the baseline systems and generate comparison-table-ready metrics:

```bash
python baseline_evaluation.py --dataset Dataset.csv
```

Run stress evaluation with a separate conflict-focused dataset (original dataset remains unchanged):

```bash
python baseline_evaluation.py --dataset Dataset_conflict_stress.csv --output-dir outputs/baseline_evaluation_conflict_stress
```

The standard holdout can legitimately report a `0.0000` logical conflict rate when none of
the baseline recommendations violate the configured conflict rules. Use the conflict-stress
dataset to verify that the metric detects contradictory recommendations; a non-zero value is
not manufactured for the standard dataset.

Generated outputs:

- `outputs/baseline_evaluation/baseline_predictions.csv`
- `outputs/baseline_evaluation/baseline_metrics.csv`
- `outputs/baseline_evaluation/comparison_table.md`
