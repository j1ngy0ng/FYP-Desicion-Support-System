# Synthetic Development Evaluation

> **Non-confirmatory result:** reference intents and actions are deterministic synthetic development annotations, not independent human labels. Do not report these values as human-validated model performance.

- Chronological holdout cases: 8,334
- Training partition: earliest 70%
- Validation partition: next 15% (not scored here)
- Test partition: latest 15%
- Proposed-system calibration status: `pending_human_annotations`

|System|Recommendation Accuracy|Scenario-Fit Rate|Logical Conflict Rate|Expected Calibration Error (ECE)|Recommendation Latency (ms)|Actionability Proxy|Trust Alignment Proxy|Explanation Usefulness Proxy|User Acceptance Proxy|
|---|---|---|---|---|---|---|---|---|---|
|Baseline A - Heuristic Scorecard|0.5784|0.9647|0.0532|0.2008|0.0030|0.8711|0.5450|0.0000|0.5392|
|Baseline B - Predictive Analytics Only|0.7101|0.9933|0.0158|0.1570|0.0127|0.9020|0.5688|0.0000|0.5599|
|Baseline C - Predictive Analytics with Attribution|0.7087|0.9935|0.0158|0.1474|0.0188|0.9038|0.5720|0.7681|0.7537|
|Baseline D - Post-Hoc Rule Overlay|0.7234|0.9958|0.0000|0.1156|0.0170|0.9197|0.5999|0.0179|0.5823|
|Proposed System - Full Framework|0.6380|1.0000|0.0004|0.2373|1.4103|0.8810|0.5016|1.0000|0.7779|
|Proposed Ablation - Without Intent|0.6144|0.9597|0.0404|0.2417|1.3641|0.8422|0.4881|1.0000|0.7577|
|Proposed Ablation - Without Rules|0.5310|0.9706|0.0624|0.1589|1.1779|0.8393|0.5132|1.0000|0.7654|
|Proposed Ablation - Without Calibration|0.6380|1.0000|0.0004|0.2373|1.4329|0.8810|0.5016|1.0000|0.7779|
|Proposed Ablation - Predictive Backbone|0.4736|0.9324|0.0979|0.1340|1.1497|0.8047|0.5220|1.0000|0.7546|

Proxy measures are deterministic technical indicators and are not participant-study results.
Because calibration remains locked pending human annotations, the full framework and without-calibration ablation are expected to use the same temperature.
