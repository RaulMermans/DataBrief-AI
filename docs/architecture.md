# Architecture

## Current slice

The current implementation is intentionally direct:

`Next.js upload UI -> FastAPI upload route -> profiler -> dataset router -> plan generator -> UI report shell`

## Boundaries

- `app/`: user-facing upload and report shell.
- `backend/main.py`: HTTP boundary.
- `backend/services/profiler.py`: deterministic CSV/XLSX profiling.
- `backend/services/router.py`: deterministic sales/generic routing.
- `backend/services/planner.py`: deterministic sales/generic analysis plans.

No queue, sandbox, LangGraph, auth, database, or model calls are part of this slice.

## Data handling

CSV/XLSX contents are read in memory for the request, profiled, sampled to five rows, and returned to the client. No uploaded file is persisted in this slice.
