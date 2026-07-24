# Dataset provenance

## Raw source

`data/layers/01_raw_dataset_55555x16.csv` is the active unchanged source copy.
Its SHA-256 digest is
`4969a1c5961fba85772822467f87e2c3069107017bdc6d685c21b47a0ed22665`,
identical to the previously audited raw source.

The raw file contains 55,555 campaign records and 16 source attributes. These
attributes are the only fields treated as observed campaign data.

## Processed model data

`data/layers/02_processed_model_data.csv` contains the same 55,555 records. The
original 16 values match the raw layer exactly. Its 15 additional fields are
non-destructive calculated model features. Audited calculations include CTR,
click-to-lead, lead-to-conversion, overall conversion, revenue ratios,
acquisition-cost and ROI proxies, performance score/band and funnel quality.

## Benchmark candidates and human annotation

`data/pilot_annotation_template.csv` contains 25 blank cases for the rubric
pilot. `data/benchmark_candidate_125.csv` contains the 125 authentic campaigns
selected by the supplied package, with blank plan-aligned reviewer fields.

For independent review, use:

- `data/annotation_packets/Reviewer_1_Annotation_Packet.xlsx`
- `data/annotation_packets/Reviewer_2_Annotation_Packet.xlsx`

Each workbook contains the same pilot and full case sets in a different order,
with controlled drop-down values and blank annotation cells.

The following fields must be entered by people:

- Reviewer 1 intent, action and notes
- Reviewer 2 intent, action and notes
- adjudicated intent, action and notes
- annotation status

No AI-generated intent, recommendation, justification, reviewer label or
reference action is permitted in the audited benchmark.

The completed benchmark must be saved as `data/benchmark_audited.csv`. The
evaluation code rejects missing, incomplete or unaudited annotations.

## Supplied review file: unverified

The supplied `03_gold_benchmark_125.csv` and review workbook are preserved as
`data/layers/03_gold_benchmark_125_unverified.csv` and
`data/layers/03_gold_benchmark_review_unverified.xlsx`. Their 125 campaign
records match the raw source and report reviewer action kappa of approximately
0.826 when calculated from the populated columns.

They are not the locked gold benchmark. The intent labels use Brand Awareness,
Lead Generation, Retention/Re-engagement, Sales Conversion and Traffic
Generation; the action labels use seven granular operational actions. These do
not match the protocol classes. The notes and data dictionary describe
deterministic rule-based interpretations, and reviewer identity, timestamps
and independence are not evidenced. One annotation status also contradicts
the documented agreement rule. Consequently these labels are excluded from
active model training, calibration and confirmatory evaluation.

The reproducible import decision is recorded by
`scripts/import_three_layer_package.py` and `data/layers/IMPORT_AUDIT.json`.

## Synthetic robustness data

`data/Dataset_conflict_stress.csv` is a synthetic robustness fixture, not a
source of ground-truth recommendation labels. Its AI-generated annotation
columns have been removed. It must not be used for confirmatory action-agreement
or calibration claims.

## Complete synthetic development annotations

`data/Dataset_synthetic_development.csv` contains all 55,555 authentic source
records plus deterministic development-only fields:

- `Reviewer_Intent`
- `Reviewer_Action`
- `Reviewer_Notes`
- `Annotation_Source`

The annotation source is written on every row as synthetic rule-based
development data. The generation thresholds and class distributions are stored
in `data/synthetic_development_summary.json`. This file may be used for
interface demonstrations, software testing and formative development only. It
must not be represented as independent human review or used for confirmatory
Cohen's kappa, calibration, actionability or practitioner-reliance claims.
