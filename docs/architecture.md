# Architecture

## Current slice

The current implementation is intentionally direct:

`Next.js upload UI -> FastAPI upload route -> profiler -> dataset router -> plan generator -> Python code generator -> sandbox runner -> UI debug/artifact shell`

## Boundaries

- `app/`: user-facing upload and report shell.
- `backend/main.py`: HTTP boundary.
- `backend/services/profiler.py`: deterministic CSV/XLSX profiling.
- `backend/services/router.py`: deterministic sales/generic routing.
- `backend/services/planner.py`: deterministic sales/generic analysis plans.
- `backend/services/codegen.py`: deterministic template-based Python generation.
- `backend/services/sandbox_runner.py`: bounded subprocess execution and artifact metadata.

No queue, LangGraph, auth, database, retry loop, report generator, or model calls are part of this slice.

## Data handling

CSV/XLSX contents are read in memory for the request, profiled, sampled to five rows, and returned to the client. For execution, uploads are copied into a request-scoped temporary CSV input; generated artifacts are saved under the OS temp directory and served by run id.
