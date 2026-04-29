# DataBrief AI

DataBrief AI is a workflow-driven analytics copilot for uploaded datasets.

The current slice supports CSV/XLSX upload, deterministic profiling, sales/ecommerce/finance/generic routing, structured analysis planning, template-based Python generation, bounded sandbox execution with artifacts, and structured user-facing failures.

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
- `POST /api/upload` with multipart field `file`

The upload endpoint returns `profile`, `route`, deterministic `plan`, generated Python code, execution logs, `retry` history, `report` summary, and artifact metadata for CSV and XLSX files.

Failures return JSON with `detail` and `error.code` fields. Expected codes include `file_too_large`, `unsupported_file`, `execution_timeout`, `invalid_upload`, and `backend_failure`.

## Deploy to Vercel

This repo uses Vercel Services to deploy the Next.js frontend and FastAPI backend from a single repository.

- Frontend is served at `/`
- Backend is served at `/backend` (e.g. `https://<your-domain>.vercel.app/backend/health`)

**Steps:**
1. Import the repo into Vercel. `vercel.json` configures both services automatically.
2. In **Project Settings → Environment Variables**, set:
   - `NEXT_PUBLIC_API_BASE_URL` → `/backend`
   - `DATABRIEF_ENV` → `production`
   - `DATABRIEF_MAX_UPLOAD_MB` → `5`
   - `DATABRIEF_CORS_ORIGINS` → `https://<your-domain>.vercel.app`
3. Deploy.

> **Note:** Vercel's serverless runtime uses request-size, memory, timeout, and ephemeral-filesystem limits. Artifact files and the SQLite run store are not persisted across invocations. Oversized uploads or long-running analyses should fail with clear error copy, but this deployment is suitable for live demos, not long-term artifact storage or large production datasets.

## Demo datasets

Upload files from `examples/` to exercise the current workflow:

- `sample_sales.csv`
- `sample_inventory.csv`
- `sample_support.csv`
