# Experiment output status

Previous metrics were calculated against AI-generated decision labels and have
been removed from the active research record.

Confirmatory outputs must not be generated until:

1. `data/benchmark_audited.csv` contains at least 120 independently reviewed
   and adjudicated cases;
2. every included row has `Annotation_Status=Audited`;
3. action-label Cohen's kappa is at least 0.60;
4. calibration is fitted only on the human-labelled validation split.

The baseline runner enforces the audited-file requirement.

`outputs/human_provided_development/` contains the explicitly
non-confirmatory comparison based on the user-supplied annotation file. It
uses an earliest-70% training, next-15% validation and latest-15% test split.
These outputs may be used to debug and compare the prototype, but not as
independently reviewed human-performance evidence.

That development run is retained as historical diagnostic output only. It is
not the active experiment after adoption of the three-layer package. New
confirmatory output remains blocked until `data/benchmark_candidate_125.csv`
is independently reviewed under the locked intent/action schema and frozen as
`data/benchmark_audited.csv`.
