# MarketSense React Application

React, Vite and TypeScript implementation of the Chapter 4 interfaces. The existing visual
design is retained while campaigns, recommendations, rules, profiles and evaluations are
loaded from the FastAPI backend.

## Run

Start the FastAPI backend from the repository root, then run:

```bash
cd system_components/presentation_layer/web_app
npx pnpm install
npx pnpm dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to `http://127.0.0.1:8000`.
