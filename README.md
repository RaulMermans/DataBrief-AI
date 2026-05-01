# DataBrief AI

**DataBrief AI** is a bounded AI analytics workflow that transforms CSV/XLSX files into structured business reports through dataset profiling, domain routing, controlled Python execution, evaluation/repair loops, and grounded report generation.

The workflow uses deterministic profiling, controlled code generation, bounded repair, and grounded report generation — not open-ended agent behavior.

## What it does

Upload → Validate → Profile → Route → Plan → Execute → Evaluate → Repair → Report → Export

1. **Upload & validate** — CSV or XLSX accepted; malformed files fail fast with clear errors.
2. **Profile** — Structural stats (row count, column types, missing values, duplicates) and semantic column roles (identifier, date, revenue, quantity, …).
3. **Route** — Dataset classified as sales, ecommerce, finance, or generic based on column roles.
4. **Plan** — Deterministic analysis plan: KPI targets, business questions, recommended charts.
5. **Execute** — Template-generated Python runs in a bounded sandbox; only allowed stdlib and pandas/numpy/matplotlib/seaborn imports are permitted.
6. **Evaluate & repair** — Up to 2 bounded repair attempts on failure; unrecoverable errors surface clearly.
7. **Report** — Structured report built from computed outputs only: no claims are invented.
8. **Export** — Download the report (Markdown), findings (JSON), and the generated analysis script (Python).

## Positioning

This project is a **bounded workflow**, not a fully autonomous AI agent. Spreadsheet analysis benefits from predictable orchestration, deterministic validation, and clear safety limits. Open-ended agents are inappropriate here because they can generate hallucinated facts, make unverifiable claims, or produce unsafe execution.

**Do not describe this project as:**
- "Fully autonomous AI agent"
- "Production-grade sandbox"
- "Universal CSV analyst"

**Sandbox note:** Network-capable imports are rejected statically, but OS-level network isolation is not implemented. Production use would require container or namespace isolation.

## Run locally

```bash
npm install
python3 -m pip install -r backend/requirements.txt
```

```bash
npm run dev
python3 -m uvicorn backend.main:app --reload
```

Open `http://localhost:3000`.

## Verify

```bash
npm run lint
npm run typecheck
pytest -q
python3 -m compileall backend
```

## API

- `GET /health`
- `POST /api/upload` — multipart field `file` (CSV or XLSX)
- `GET /api/runs/{run_id}/export/report.md`
- `GET /api/runs/{run_id}/export/findings.json`
- `GET /api/runs/{run_id}/export/analysis.py`

The upload endpoint returns `run_id`, `profile`, `route`, `plan`, `codegen`, `execution`, `retry`, and `report`. Failures return JSON with `detail` and `error.code`.

## Demo datasets

Download from `examples/` and upload to exercise the workflow:

- `sample_ecommerce.csv` — 30 purchase lines across footwear, sports, and apparel categories with date, category, quantity, and unit price.
- `sample_performance.csv` — 25 sales rep records with territory, product line, revenue, quota, and new-customer flag.
- `sample_campaigns.csv` — 26 campaign rows across paid search, social, display, and email with impressions, clicks, conversions, and spend.
- `sample_sales.csv` — Simple 4-row sales CSV for quick smoke tests.
- `sample_inventory.csv` — Inventory dataset.
- `sample_support.csv` — Support ticket dataset.

## Deploy to Vercel

This repo uses Vercel Services to deploy the Next.js frontend and FastAPI backend from a single repository.

1. Import the repo into Vercel. `vercel.json` configures both services automatically.
2. In **Project Settings → Environment Variables**, set:
   - `NEXT_PUBLIC_API_BASE_URL` → `/backend`
   - `DATABRIEF_ENV` → `production`
   - `DATABRIEF_MAX_UPLOAD_MB` → `5`
   - `DATABRIEF_CORS_ORIGINS` → `https://<your-domain>.vercel.app`
3. Deploy.

> **Note:** Vercel's serverless runtime has request-size, memory, timeout, and ephemeral-filesystem limits. Artifact files and the SQLite run store are not persisted across invocations. Suitable for live demos, not long-term artifact storage.
