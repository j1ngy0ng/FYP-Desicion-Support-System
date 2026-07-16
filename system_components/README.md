# System Components

This directory follows the five-layer architecture in Chapter 4, Figure 4.1 of the
FYP report. Dependencies flow from presentation through trust and decision support,
neuro-symbolic reasoning, predictive analytics, and data management.

Executable components are stored in their matching architecture directories:

- `data_management_layer/campaign_data`: SQLAlchemy database and domain entities.
- `data_management_layer/data_preprocessing`: dataset validation and derived features.
- `predictive_analytics_layer/predictive_attribution`: PyTorch model and attribution.
- `neuro_symbolic_reasoning_layer`: candidate generation, weighted rules, intent ranking,
  and the recommendation pipeline orchestrator.
- `trust_and_decision_layer`: temperature calibration and structured explanations.
- `presentation_layer`: React dashboard, campaign analysis, recommendation viewer, and web shell.

`backend/app` now contains the FastAPI application and thin compatibility imports only.
