# Baseline Comparison Metrics

This table is generated from `Dataset_conflict_stress.csv` using Chapter 3 baseline configurations and metrics.

|Baseline|Recommendation Accuracy|Scenario-Fit Rate|Logical Conflict Rate|Expected Calibration Error (ECE)|Recommendation Latency (ms)|Actionability Proxy|Trust Alignment Proxy|Explanation Usefulness Proxy|User Acceptance Proxy|
|---|---|---|---|---|---|---|---|---|---|
|Baseline A - Heuristic Scorecard|0.5200|0.7600|0.2800|0.2046|0.0057|0.6888|0.5088|0.0000|0.4536|
|Baseline B - Predictive Analytics Only|0.6400|0.8000|0.1200|0.1999|0.0179|0.7774|0.5576|0.0000|0.5061|
|Baseline C - Predictive Analytics with Attribution|0.7200|0.8000|0.0800|0.2361|0.0303|0.7927|0.5392|0.7480|0.6928|
|Baseline D - Post-Hoc Rule Overlay|0.5200|0.8000|0.0000|0.1940|0.0242|0.8438|0.5607|0.0490|0.5460|

## Notes
- Baseline A: heuristic scorecard (manual threshold logic).
- Baseline B: predictive-only centroid classifier.
- Baseline C: predictive + channel attribution adjustment.
- Baseline D: predictive ranking followed by hard post-hoc conflict filtering.
- Proxy metrics are deterministic technical indicators, not results from human participants.