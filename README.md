# DataBrief AI

DataBrief AI is a workflow-driven analytics copilot for uploaded datasets.

This first vertical slice supports CSV upload, deterministic profiling, sales/generic routing, and a report shell UI.

## Run locally

```bash
npm install
python -m pip install -r backend/requirements.txt
```

```bash
npm run dev
python -m uvicorn backend.main:app --reload
```

Open `http://localhost:3000`.

## Verify

```bash
npm run lint
npm run typecheck
pytest -q
python -m compileall backend
```

## API

- `GET /health`
- `POST /api/upload` with multipart field `file`

The upload endpoint returns `profile` and `route` payloads for CSV files.
