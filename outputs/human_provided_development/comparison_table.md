# Human-Provided Development Evaluation

> **Non-confirmatory result:** the annotations were supplied as human-labelled, but reviewer independence, adjudication and audit status are not documented. Do not report these values as independently human-validated performance.

- Chronological holdout cases: 8,334
- Training partition: earliest 70%
- Validation partition: next 15% (not scored here)
- Test partition: latest 15%
- Proposed-system calibration status: `pending_human_annotations`

|System|Recommendation Accuracy|Scenario-Fit Rate|Logical Conflict Rate|Expected Calibration Error (ECE)|Recommendation Latency (ms)|Actionability Proxy|Trust Alignment Proxy|Explanation Usefulness Proxy|User Acceptance Proxy|
|---|---|---|---|---|---|---|---|---|---|
|Baseline A - Heuristic Scorecard|0.1141|0.9580|0.0620|0.4230|0.0058|0.8650|0.4350|0.0000|0.4982|
|Baseline B - Predictive Analytics Only|0.8498|0.9422|0.1194|0.0473|0.0160|0.8927|0.7526|0.0000|0.6205|
|Baseline C - Predictive Analytics with Attribution|0.8477|0.9460|0.1128|0.0476|0.0297|0.8965|0.7506|0.7681|0.8133|
|Baseline D - Post-Hoc Rule Overlay|0.8713|1.0000|0.0000|0.0668|0.0228|0.9820|0.8230|0.0578|0.6953|
|Proposed System - Full Framework|0.9087|1.0000|0.0224|0.4688|4.9762|0.8801|0.4585|1.0000|0.7625|
|Proposed Ablation - Without Intent|0.8397|1.0000|0.0091|0.4413|4.8939|0.8771|0.4425|1.0000|0.7557|
|Proposed Ablation - Without Rules|0.9552|1.0000|0.0679|0.5564|4.7176|0.8560|0.4130|1.0000|0.7369|
|Proposed Ablation - Without Calibration|0.9087|1.0000|0.0224|0.4688|4.6553|0.8801|0.4585|1.0000|0.7625|
|Proposed Ablation - Predictive Backbone|0.9228|1.0000|0.0492|0.5468|4.2202|0.8580|0.4028|1.0000|0.7342|

Proxy measures are deterministic technical indicators and are not participant-study results.
Because calibration remains locked pending human annotations, the full framework and without-calibration ablation are expected to use the same temperature.
