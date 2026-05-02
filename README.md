# DataBrief AI

**DataBrief AI** is a bounded AI analytics workflow for CSV/XLSX files. It uses deterministic profiling, semantic role detection, controlled Python execution, bounded repair, and grounded report generation.

> **Portfolio prototype.** This project is a technical case study demonstrating bounded AI workflow design — not a production SaaS, not a fully autonomous agent, and not an enterprise-ready analytics platform. See [Current Limitations](#current-limitations).

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

This project uses a **bounded workflow**, not a fully autonomous AI agent. Spreadsheet analysis benefits from predictable orchestration, deterministic validation, and clear safety limits. Open-ended agents can generate hallucinated KPIs, make unverifiable claims, or produce unsafe code — none of which belong in analytics.

## Screenshots

> Screenshots from the demo deployment using `examples/sample_ecommerce.csv`.

See [docs/screenshots/](docs/screenshots/) for portfolio-ready screenshots of the upload screen, semantic profile, report, and export buttons.

## Run locally

```bash
# Install dependencies
npm install
python3 -m pip install -r backend/requirements.txt

# Optional: install openpyxl for XLSX support
python3 -m pip install openpyxl
```

```bash
# Start frontend
npm run dev

# Start backend (from the backend/ directory)
cd backend && uvicorn main:app --reload
```

Open `http://localhost:3000`.

Copy `.env.example` to `.env` and adjust if needed (defaults work for local dev).

## Verify

```bash
# Linting and type checks
npm run lint
npm run typecheck

# Full test suite
pytest -q

# Semantic quality and planner tests specifically
pytest backend/tests/test_semantic_quality.py backend/tests/test_semantic_profile.py backend/tests/test_planner.py -q

# Python syntax check
python3 -m compileall backend
```

> **Note:** XLSX tests require `openpyxl`. If it is not installed, those tests are skipped with a clear message.

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

All datasets are synthetic. No real customer or company data.

## Current limitations

- **Portfolio prototype, not production SaaS.** This is a technical demo with a focused feature set.
- **No OS-level sandbox isolation.** See sandbox note below.
- **No order-level metrics without an order ID.** True order count and average order value require an order ID column; without one, the workflow uses "purchase line count" and flags the limitation.
- **Return/cancel rate requires a status field.** Without a return, refund, cancel, or status column, the metric is labeled "Unavailable."
- **Analysis quality depends on detectable column roles.** Ambiguous or non-standard column names degrade routing and plan quality.
- **No full autonomous agentic reasoning.** The pipeline is deterministic and orchestrated; it does not reason freely across unknown schemas.
- **Single-run, no memory.** Each upload is independent; there is no cross-run analysis or session persistence.
- **File size cap.** Demo deployment caps uploads at 5 MB; large files require local deployment.

## Sandbox note

Generated code is statically checked and executed with resource limits. Network-capable imports and suspicious patterns are rejected, but OS-level network/filesystem isolation is not implemented. Production use would require container isolation, network namespace restrictions, filesystem mount controls, and stronger process sandboxing.

## Future improvements

- True OS-level sandbox isolation (Docker or seccomp)
- Streaming workflow status to the frontend
- Persistent run history for multi-upload comparison
- User-configurable analysis focus (e.g., "focus on geographic breakdown")
- Support for multi-sheet XLSX files
- Richer evaluation fixture suite
- More domain-specific analysis recipes

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

## Architecture

See [docs/architecture.md](docs/architecture.md) and [docs/case-study.md](docs/case-study.md) for detailed design notes.
