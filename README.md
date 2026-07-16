# FYP-Desicion-Support-System
Intent-Aware Logic-Constrained Neuro-Symbolic Decision Support System with Trust Calibration for SME Multi-Channel Marketing

## Baseline evaluation (Chapter 3)

Run the baseline systems and generate comparison-table-ready metrics:

```bash
python baseline_evaluation.py
```

Run stress evaluation with a separate conflict-focused dataset (original dataset remains unchanged):

```bash
python baseline_evaluation.py --dataset data/Dataset_conflict_stress.csv --train-dataset data/Dataset.csv --output-dir outputs/conflict_stress
```

The standard holdout can legitimately report a `0.0000` logical conflict rate when none of
the recommendations violate the configured conflict rules. The conflict-stress evaluation
trains on the normal dataset and tests on unseen stressed cases, so it measures robustness
without leaking stress examples into model fitting.

Generated outputs:

- `outputs/normal/` contains the normal-dataset results.
- `outputs/conflict_stress/` contains the robustness-test results.

Logical Conflict Rate uses the predefined, system-independent catalogue in
[`docs/CONFLICT_RULES.md`](docs/CONFLICT_RULES.md). Prediction outputs include a conflict flag and
the exact rule identifiers triggered for each baseline recommendation.

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
- PyTorch predictive model with feature and campaign-level channel attribution.
- Four bounded actions: Increase, Maintain, Decrease and Investigate.
- Weighted soft-rule reasoning, Survival/Retention/Growth intent ranking, validation-based
  temperature scaling and Driver/Implication/Action/Caveat explanations.
- Frozen-holdout baseline comparison, four ablation configurations and human feedback logging.

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

The current academic dataset contains 125 records, below the report's 500-record target.
The Evaluation screen therefore labels the experiment as a simplified configuration; the
software does not overstate multi-channel generalisability.

All systems use the same seeded holdout and the same consensus-or-reference ground-truth
labels. Scoring parameters and calibration are selected on validation data only. Stress
evaluation trains on the normal dataset, and the interface reports 95% bootstrap confidence
intervals. Technical actionability and explanation scores are labelled as proxies; participant
ratings are stored and reported separately.
