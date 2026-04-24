# DataBrief AI

DataBrief AI is a workflow-driven analytics copilot for uploaded datasets.

The current slice supports CSV/XLSX upload, deterministic profiling, sales/generic routing, and a structured analysis plan shell.

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

The upload endpoint returns `profile`, `route`, and deterministic `plan` payloads for CSV and XLSX files.

## Demo datasets

Upload files from `examples/` to exercise the current workflow:

- `sample_sales.csv`
- `sample_inventory.csv`
- `sample_support.csv`
