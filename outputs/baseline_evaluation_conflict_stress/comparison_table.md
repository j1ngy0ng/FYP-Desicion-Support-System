# Baseline Comparison Metrics

This table is generated from `Dataset_conflict_stress.csv` using Chapter 3 baseline configurations and metrics.

|Baseline|Recommendation Accuracy|Scenario-Fit Rate|Logical Conflict Rate|Expected Calibration Error (ECE)|Recommendation Latency (ms)|Recommendation Actionability|Trust Alignment|Explanation Usefulness|User Acceptance|
|---|---|---|---|---|---|---|---|---|---|
|Baseline A - Heuristic Scorecard|0.5000|0.7692|0.2308|0.1825|0.0042|0.7094|0.5134|0.0000|0.4635|
|Baseline B - Predictive Analytics Only|0.5769|0.8077|0.1154|0.1828|0.0135|0.7881|0.5415|0.0000|0.5048|
|Baseline C - Predictive Analytics with Attribution|0.6154|0.8077|0.1923|0.0794|0.0207|0.7659|0.5319|0.7577|0.6820|

## Notes
- Baseline A: heuristic scorecard (manual threshold logic).
- Baseline B: predictive-only centroid classifier.
- Baseline C: predictive + channel attribution adjustment.
- Human metrics are computed as reproducible proxy scores from model outputs for comparison-table preparation.