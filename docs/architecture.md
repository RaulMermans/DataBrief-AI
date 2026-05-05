# Architecture

## Overview

DataBrief AI is a **bounded AI analytics workflow**, not an open-ended analysis
system.  Every step is deterministic, explicitly sequenced, and capped with strict stop
conditions.  There are no unbounded loops, no open-ended model prompts, and no
external network access in the analysis path.

## Workflow steps

```
upload
  → validate file (CSV/XLSX, size limit)
  → profile dataset (types, missing, duplicates)
  → route dataset type (sales | ecommerce | finance | generic)
  → generate analysis plan
  → generate Python from controlled template
  → validate code (AST import + suspicious-pattern checks)
  → execute in sandbox (subprocess, resource limits)
  → evaluate execution (success | recoverable | unrecoverable)
  → bounded repair loop (max 2 repairs, deterministic fixes only)
  → validate summary.json schema
  → generate grounded report
  → groundedness revision (claim/evidence, single pass)
  → store run metadata (SQLite)
  → serve exports (report.md, findings.json, analysis.py, artifacts)
```

## Service boundaries

| File | Responsibility |
|------|---------------|
| `backend/main.py` | HTTP boundary, request routing, lifespan hooks |
| `backend/config.py` | Env-var settings with validation |
| `backend/services/profiler.py` | Deterministic CSV/XLSX profiling |
| `backend/services/router.py` | Deterministic sales/ecommerce/finance/generic routing |
| `backend/services/planner.py` | Deterministic domain-specific analysis plans |
| `backend/services/codegen.py` | Template-based Python generation + repair variants |
| `backend/services/sandbox_runner.py` | Bounded subprocess execution, artifact metadata, cleanup |
| `backend/services/evaluator.py` | Execution outcome + failure-type classification |
| `backend/services/retry_runner.py` | Bounded repair loop (max 2 repairs) |
| `backend/services/summary_validator.py` | Schema validation of summary.json artifacts |
| `backend/services/report_generator.py` | Grounded report from computed outputs only |
| `backend/services/groundedness.py` | Claim/evidence model, single-pass revision |
| `backend/services/run_store.py` | SQLite run metadata, export helpers, TTL expiry |

## Data handling

Uploaded file bytes are held in memory for the request lifetime, profiled, and
sampled to five rows for UI display.  The file is written to a temp directory
as a CSV for sandbox execution only; it is deleted immediately after the repair
loop completes.  Artifacts are saved under `{OS_TEMP}/databrief-ai-runs/{run_id}/`.

## Sandbox execution boundary

Generated scripts run in a child `subprocess` with `python -I` (isolated mode,
no user-site packages), a stripped environment (no `HOME`, `PATH`, etc.), and
POSIX resource limits (`RLIMIT_AS`, `RLIMIT_CPU`).

**AST import policy (pre-execution):**  `validate_imports` parses the script
with the stdlib `ast` module and rejects any top-level import not on the
approved allowlist before a subprocess is spawned.

**Suspicious-pattern checks (pre-execution):**  `validate_suspicious_patterns`
additionally rejects: `eval`, `exec`, `compile`, `__import__` calls;
`os.system`, `os.popen`, `os.environ`, `os.execv*`, `os.fork` access;
hardcoded absolute paths in system directories (`/etc/`, `/home/`, `/root/`).

**Approved top-level imports:** `builtins`, `collections`, `csv`, `datetime`,
`html`, `json`, `math`, `pathlib`, `statistics`, `sys`, `pandas`, `numpy`,
`matplotlib`, `seaborn`.

**Network:** Not blocked at the OS level.  The primary defence is the AST
import policy: `socket`, `urllib`, `requests`, `httpx` are not on the approved
list and are rejected before any subprocess runs.  True production hardening
requires OS-level isolation (container / network namespace / seccomp).

**Resource limits (POSIX only):** `RLIMIT_AS` and `RLIMIT_CPU` via
`resource.setrlimit`; `subprocess.timeout` enforced independently.

## Bounded repair loop

1. Execute the initially generated code.
2. On recoverable failure, `classify_failure_type` identifies: `missing_column`,
   `date_parsing`, `chart_error`, `numeric_error`, `empty_output`, or
   `generic_runtime`.
3. `apply_codegen_repair` modifies the codegen context (e.g. `skip_charts=True`,
   removes problematic columns, clears `date_columns`) and re-generates code
   within the same template family.
4. Re-validate, re-execute.  Maximum 2 repair attempts (3 total executions).
5. Unrecoverable failures (`import_policy`, `syntax_error`, repeated `timeout`)
   stop immediately without retrying.

All attempts and repair instructions are recorded in `retry_history` for
auditability.

## Groundedness model

Every claim in the report is converted to a `GroundedClaim` object with:
- `claim`: the text of the claim
- `claim_type`: `kpi | finding | summary | recommendation`
- `source`: the specific field in `summary.json` or profile that backs the claim
  (e.g. `summary.json:kpis.Total revenue`)
- `status`: `supported | unsupported | uncertain`
- `reason`: why the status was assigned

Unsupported claims are removed from the report.  The claim list is attached to
the report payload for auditability.  Revision is capped at one pass.

## Run metadata (SQLite)

Each run is persisted in `{OS_TEMP}/databrief-ai-runs/runs.db` with:
`run_id`, `status`, `filename`, `profile/route/plan_json`, `retry_count`,
`evaluation_json`, `report_json`, `generated_code`, `summary_errors`,
`created_at`, `expires_at`.

Status values: `uploaded → executing → evaluating → complete | partial | failed | expired`.

TTL is configurable via `DATA_RUN_TTL_HOURS` (default 24h).  Cleanup runs on
every server startup.

## Public API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/upload` | Upload CSV/XLSX, run full pipeline |
| GET | `/api/runs/{run_id}` | Poll run status |
| GET | `/api/runs/{run_id}/artifacts/{name}` | Serve artifact file |
| GET | `/api/runs/{run_id}/export/report.md` | Download report as Markdown |
| GET | `/api/runs/{run_id}/export/findings.json` | Download structured findings |
| GET | `/api/runs/{run_id}/export/analysis.py` | Download generated Python script |

API responses **never expose host filesystem paths**.  `ArtifactMetadata`
omits the internal `path` field; only `name`, `size_bytes`, `content_type`,
and `url` are returned.

Upload and workflow failures return structured JSON with `detail` and
`error.code`. The frontend treats non-JSON hosting/proxy failures as backend
limit failures instead of surfacing raw JSON parse errors.

## Security model

- Uploads, model outputs, and generated code are treated as untrusted.
- Sandbox is offline, allowlisted, and resource-bounded.
- Generated code is statically validated before any subprocess is spawned.
- No host filesystem paths are exposed in API responses.
- Secrets are in `.env`; `.env.example` documents required vars.
- PII-sensitive by default: prefer derived summaries over raw row persistence.
- **Production hardening note:** OS-level isolation (container, seccomp,
  network namespace) is required for untrusted inputs in production.
  The current sandbox provides defence-in-depth but not OS-level containment.

## Known limitations

- The sandbox does not block network at the OS level (AST import check is the
  primary defence).
- The repair loop can fix common template-compatible failures but cannot repair
  structurally broken data or logic bugs.
- SQLite is sufficient for demo/local scale; a proper DB is needed for
  multi-worker deployments.
- The system does not support multi-user or concurrent access patterns.
- Chart generation is SVG-only with a simple custom renderer (no matplotlib
  dependency in the sandbox template).
- Demo deployments on Vercel remain subject to platform request-size, memory,
  timeout, and ephemeral-filesystem limits. Large datasets should be reduced or
  handled by a more durable backend deployment.

## Evaluation strategy

Deterministic graders are preferred over LLM judges:
- Schema validation (summary.json required fields)
- Status assertions (exit code, artifact existence)
- Sandbox rejection assertions (import policy, suspicious patterns)
- Groundedness claim status checks (supported/unsupported)
- Export endpoint response checks

See `backend/tests/` for the full test suite (124 tests as of Phase 6).
