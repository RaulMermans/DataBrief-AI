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

No queue, LangGraph, auth, database, or model calls are part of this slice. (A bounded retry loop and a report generator were added in Phase 5).

## Data handling

CSV/XLSX contents are read in memory for the request, profiled, sampled to five rows, and returned to the client. For execution, uploads are copied into a request-scoped temporary CSV input; generated artifacts are saved under the OS temp directory and served by run id.

## Sandbox execution boundary

Generated scripts run in a child `subprocess` with `python -I` (isolated mode, no user-site packages).

**Import policy (AST-based, pre-execution):** `sandbox_runner.validate_imports` parses the generated script with the stdlib `ast` module and rejects any top-level import not on the approved allowlist before a subprocess is spawned. This replaces a previous `builtins.__import__` runtime monkeypatch that was brittle against stdlib internal lazy imports (e.g. `_io`, `ntpath`).

**Approved top-level imports:** `builtins`, `collections`, `csv`, `datetime`, `html`, `json`, `math`, `pathlib`, `statistics`, `sys`, `pandas`, `numpy`, `matplotlib`, `seaborn`.

**Network:** Not blocked at the OS level (no network namespace, seccomp, or iptables rules). The primary defence is the AST import policy: `socket`, `urllib`, `requests`, `httpx`, and similar networking modules are not on the approved list and are rejected before any subprocess runs.

**Resource limits (POSIX only):** `RLIMIT_AS` and `RLIMIT_CPU` via `resource.setrlimit`; `subprocess.timeout` enforced independently.
