# Baseline Comparison Metrics

This table is generated from `Dataset.csv` using Chapter 3 baseline configurations and metrics.

|Baseline|Recommendation Accuracy|Scenario-Fit Rate|Logical Conflict Rate|Expected Calibration Error (ECE)|Recommendation Latency (ms)|Actionability Proxy|Trust Alignment Proxy|Explanation Usefulness Proxy|User Acceptance Proxy|
|---|---|---|---|---|---|---|---|---|---|
|Baseline A - Heuristic Scorecard|0.6154|1.0000|0.0385|0.1553|0.0070|0.8906|0.5598|0.0000|0.5522|
|Baseline B - Predictive Analytics Only|0.7308|0.9615|0.0769|0.2531|0.0239|0.8641|0.5181|0.0000|0.5270|
|Baseline C - Predictive Analytics with Attribution|0.7308|0.9231|0.1538|0.2285|0.0372|0.8232|0.5340|0.7981|0.7157|

## Notes
- Baseline A: heuristic scorecard (manual threshold logic).
- Baseline B: predictive-only centroid classifier.
- Baseline C: predictive + channel attribution adjustment.
- Proxy metrics are deterministic technical indicators, not results from human participants.