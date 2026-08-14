# Experiment Results

## R001 — Source audit and benchmark freeze

- Status: passed (125 audited cases)
- Intent Cohen's kappa: 0.854
- Action Cohen's kappa: 0.702

## R002 — Baseline and proposed-system technical evaluation

- Split: chronological 70/15/15 (19 held-out test cases)
- Seeds: 42, 52, 62
- Claim status: meets_initial_technical_success_criterion

|System|Macro F1|Accuracy|Top-2|Scenario Fit|Conflict|ECE|P95 ms|
|---|---:|---:|---:|---:|---:|---:|---:|
|Baseline A - Heuristic Scorecard|0.4722|0.5263|0.6316|1.0000|0.1053|0.2874|0.010|
|Baseline B - Predictive Analytics Only|0.6003|0.6316|0.9474|0.8947|0.2105|0.0553|0.020|
|Baseline C - Predictive Analytics with Attribution|0.6003|0.6316|1.0000|0.8947|0.2105|0.0684|0.026|
|Baseline D - Post-Hoc Rule Overlay|0.6444|0.6316|0.8421|1.0000|0.0000|0.0742|0.027|
|Proposed System - Full Framework|0.8279|0.8246|1.0000|1.0000|0.0000|0.2264|3.205|
|Proposed Ablation - Without Intent|0.7514|0.7368|0.9825|0.9474|0.0526|0.1942|3.534|
|Proposed Ablation - Without Rules|0.9308|0.9298|1.0000|1.0000|0.1053|0.3190|3.159|
|Proposed Ablation - Without Calibration|0.8279|0.8246|1.0000|1.0000|0.0000|0.4236|3.675|
|Proposed Ablation - Predictive Backbone|0.7831|0.7895|0.9474|0.8947|0.2105|0.3984|3.666|

Human actionability, willingness-to-act, trust-alignment and overtrust claims remain pending the blinded 18–24 participant study.
