# FYP-Desicion-Support-System
Intent-Aware Logic-Constrained Neuro-Symbolic Decision Support System with Confidence Calibration and Reliance Support for SME Multi-Channel Marketing

## Research data and evaluation gate

The active three-layer package is stored under `data/layers/`:

- `01_raw_dataset_55555x16.csv`: 55,555 unchanged source records and 16 fields.
- `02_processed_model_data.csv`: the same records plus validated, non-destructive
  calculated features used by the predictive model.
- `03_gold_benchmark_125_unverified.csv`: the supplied labelled file, preserved
  for audit but not promoted as gold evidence.

`data/benchmark_candidate_125.csv` retains the supplied 125 campaign selections
with blank plan-aligned reviewer fields. Data lineage and the import decision
are documented in `data/DATA_PROVENANCE.md` and
`data/layers/IMPORT_AUDIT.json`.

The independent human-annotation protocol is complete:

1. Run the 25-case rubric pilot in `data/pilot_annotation_template.csv`.
2. Independently label the 125 cases in
   `data/benchmark_annotation_template.csv`.
3. Adjudicate disagreements under `docs/HUMAN_ANNOTATION_RUBRIC.md`.
4. Reach Cohen's kappa of at least 0.60.
5. Save the frozen result as `data/benchmark_audited.csv`.

The frozen benchmark is `data/benchmark_audited.csv`. It contains 125
adjudicated cases, with intent Cohen's kappa of 0.854 and action Cohen's kappa
of 0.702. Reviewer and adjudicator attestations are retained under
`data/human_annotations/completed/`.

Run the complete chronological, three-seed technical evaluation with:

```bash
python -m scripts.run_confirmatory_evaluation
```

The runner rejects missing, incomplete, unaudited or legacy AI-labelled files,
fits calibration on the validation partition only, and writes R001/R002 outputs
under `results/`, `logs/`, `refine-logs/` and `outputs/confirmatory_evaluation/`.

### Benchmark review status

The originally supplied incompatible labels remain quarantined for audit. The
same 125 authentic source cases were independently re-annotated using the
locked Survival/Retention/Growth and
Increase/Maintain/Reduce/Investigate rubric, adjudicated by a third human
reviewer, and frozen after exceeding the action-kappa threshold.

## Project structure

- `data/`: normal and conflict-stress datasets.
- `docs/`: FYP report and logical-conflict rule catalogue.
- `tests/`: automated evaluation-rule tests.
- `outputs/`: generated results separated by experiment.
- `system_components/`: executable Chapter 4 implementation grouped into five architectural layers.

## Full-stack proposed system

The Chapter 3 methodology and Chapter 4 architecture are implemented as a human-in-the-loop
web application:

- React, Vite and TypeScript presentation layer using the existing MarketSense interface.
- FastAPI REST API with signed sessions and role-protected rule management.
- MySQL persistence through SQLAlchemy for users, campaigns, intents, rules,
  recommendations, activated rules and evaluations.
- PyTorch ROI regression, local predictive sensitivity and training-derived channel evidence trained from the
  validated processed model-data layer. Unverified reviewer labels are not
  active model inputs.
- Four bounded actions: Increase, Maintain, Reduce and Investigate.
- Weighted soft-rule reasoning, manager-selected Survival/Retention/Growth
  intent ranking and Driver/Implication/Action/Caveat explanations.
- A hard calibration/evaluation gate: evidence scores are displayed as
  uncalibrated until the human benchmark is frozen.

### Run locally

For the quickest local run without configuring a MySQL account, start FastAPI with SQLite:

```powershell
$env:DATABASE_URL = "sqlite:///./marketsense.db"
$env:TOKEN_SECRET = "replace-with-a-long-random-secret"
.venv\Scripts\python -m uvicorn backend.app.main:app --reload
```

The application logic and database schema are the same. Use MySQL for the final deployment and
reported technology configuration.

Start MySQL 8. The included Docker configuration is the shortest setup when Docker is available:

```powershell
docker compose up -d mysql
```

Create the backend environment and start FastAPI from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
$env:DATABASE_URL = "mysql+pymysql://marketsense:marketsense@127.0.0.1:3306/marketsense"
$env:TOKEN_SECRET = "replace-with-a-long-random-secret"
.venv\Scripts\python -m uvicorn backend.app.main:app --reload
```

In a second terminal, start the unchanged interface as a React application:

```powershell
cd system_components\presentation_layer\web_app
npx pnpm install
npx pnpm dev
```

This requires Node.js 20.19 or newer. Using `npx pnpm` avoids requiring a separate
global pnpm installation.

Open `http://127.0.0.1:5173` and sign in with `jingyong@example.com` / `prototype`.
Tables are created and the initial intents, campaigns and complete rule catalogue are seeded
automatically on first startup.

### Verify

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m unittest discover -s backend\tests -v
cd system_components\presentation_layer\web_app
npx pnpm build
```

The source dataset contains 55,555 records and passes the source-audit gate.
The 125-row file is the decision-case sample, not the full source dataset.

The Evaluation screen now provides an explicit R001-R006 run register:

- R001 shows source lineage, benchmark size and inter-rater agreement.
- R002 reports the frozen baseline and proposed-system technical comparison.
- R003 compares calibrated and uncalibrated conditions and gates appropriate-
  reliance claims on participant responses.
- R004 compares no-logic, post-hoc filtering and weighted soft-rule reasoning.
- R005 compares global, intent-conditioned and full-framework policies.
- R006 compares a terse feature list, a structured Driver-Implication-Action
  explanation and the same explanation with a confidence caveat.

The participant interface counterbalances six presentation conditions across
nine cases while preserving a single nine-case session per pseudonymous
participant. It records actionability, specificity, feasibility, explanation
usefulness, trust alignment, overtrust, acceptance, willingness to review and
decision time. Administrators can export an anonymised analysis-ready CSV from
the Evaluation screen; free-text comments are excluded from that export.

Participant outcomes remain pending until at least 18 participants complete all
nine cases. The interface reports this gate explicitly and does not infer human
trust or actionability results from the technical benchmark.
