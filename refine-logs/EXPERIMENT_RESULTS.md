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
|Supervisor Baseline - Intent-Only Deterministic|0.5938|0.6842|0.7895|1.0000|0.1053|0.3158|0.002|
|Supervisor Baseline - Weighted Deterministic|0.5071|0.5789|0.8421|1.0000|0.1053|0.0620|0.022|
|B1: Heuristic Scorecard|0.4722|0.5263|0.7895|1.0000|0.1053|0.2874|0.008|
|B2: Predictive Only|0.6003|0.6316|0.9474|0.8947|0.2105|0.0553|0.018|
|B3: Predictive plus Channel Evidence|0.6003|0.6316|1.0000|0.8947|0.2105|0.0684|0.024|
|Post-hoc Hard-Rule Filter|0.6444|0.6316|0.8421|1.0000|0.0000|0.0742|0.022|
|Proposed System - Full Framework|0.8279|0.8246|0.8947|1.0000|0.0000|0.5187|3.452|
|Branch Ablation - CampaignNet Only|0.3697|0.4386|0.5263|0.9474|0.1228|0.0875|3.003|
|Branch Ablation - ActionNet Only|0.9087|0.9123|1.0000|1.0000|0.1053|0.4702|2.669|
|Branch Ablation - Fused CampaignNet-ActionNet|0.9308|0.9298|1.0000|1.0000|0.1053|0.5354|2.704|
|Proposed Ablation - Without Intent|0.7514|0.7368|0.8772|0.9474|0.0526|0.5030|3.023|
|Proposed Ablation - Without Rules|0.9308|0.9298|1.0000|1.0000|0.1053|0.6482|3.270|
|Proposed Ablation - Without Calibration|0.8279|0.8246|0.8947|1.0000|0.0000|0.2942|3.879|
|B4: Integrated Learned Backbone|0.7831|0.7895|0.9474|0.8947|0.2105|0.3984|3.529|

Human actionability, willingness-to-act, trust-alignment and overtrust claims remain pending the blinded 18–24 participant study.
