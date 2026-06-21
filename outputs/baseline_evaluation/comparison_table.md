# Baseline Comparison Metrics

This table is generated from `Dataset.csv` using Chapter 3 baseline configurations and metrics.

|Baseline|Recommendation Accuracy|Scenario-Fit Rate|Logical Conflict Rate|Expected Calibration Error (ECE)|Recommendation Latency (ms)|Recommendation Actionability|Trust Alignment|Explanation Usefulness|User Acceptance|
|---|---|---|---|---|---|---|---|---|---|
|Baseline A - Heuristic Scorecard|0.5926|1.0000|0.0000|0.1358|0.0037|0.9030|0.5623|0.0000|0.5580|
|Baseline B - Predictive Analytics Only|0.8148|0.9630|0.0000|0.1857|0.0096|0.9195|0.6039|0.0000|0.5792|
|Baseline C - Predictive Analytics with Attribution|0.7407|0.9259|0.0000|0.0611|0.0143|0.9026|0.6017|0.8056|0.7730|

## Notes
- Baseline A: heuristic scorecard (manual threshold logic).
- Baseline B: predictive-only centroid classifier.
- Baseline C: predictive + channel attribution adjustment.
- Human metrics are computed as reproducible proxy scores from model outputs for comparison-table preparation.