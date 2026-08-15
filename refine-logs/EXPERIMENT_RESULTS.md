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
|Baseline B - Predictive Analytics Only|0.6003|0.6316|0.9474|0.8947|0.2105|0.0553|0.019|
|Baseline C - Predictive Plus Channel Evidence|0.6003|0.6316|1.0000|0.8947|0.2105|0.0684|0.027|
|Baseline D - Post-Hoc Rule Overlay|0.6444|0.6316|0.8421|1.0000|0.0000|0.0742|0.033|
|Proposed System - Full Framework|0.8279|0.8246|1.0000|1.0000|0.0000|0.2264|3.427|
|Branch Ablation - CampaignNet Only|0.3697|0.4386|0.5263|0.9474|0.1228|0.0875|3.230|
|Branch Ablation - ActionNet Only|0.9087|0.9123|1.0000|1.0000|0.1053|0.4702|3.100|
|Branch Ablation - Fused CampaignNet-ActionNet|0.9308|0.9298|1.0000|1.0000|0.1053|0.5354|3.549|
|Proposed Ablation - Without Intent|0.7514|0.7368|0.9825|0.9474|0.0526|0.1942|3.853|
|Proposed Ablation - Without Rules|0.9308|0.9298|1.0000|1.0000|0.1053|0.3190|3.547|
|Proposed Ablation - Without Calibration|0.8279|0.8246|1.0000|1.0000|0.0000|0.4236|4.685|
|Proposed Ablation - Predictive Backbone|0.7831|0.7895|0.9474|0.8947|0.2105|0.3984|4.556|

Human actionability, willingness-to-act, trust-alignment and overtrust claims remain pending the blinded 18–24 participant study.
