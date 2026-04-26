# AGENTS.md

## Product
DataBrief AI = workflow-driven analytics copilot for CSV/XLSX uploads.
Output: profile, plan, Python analysis, sandboxed execution, grounded report, exports.

## Build mode
- Build a **workflow**, not a general autonomous agent.
- Keep steps deterministic unless bounded agentic behavior clearly helps.
- Optimize for reliability, legibility, and demo quality.

## Core flow
`validate → profile → route → plan → codegen → validate_code → execute → evaluate → repair_loop → validate_summary → summarize → groundedness_check → store → export`

## Allowed agentic behavior
- Dataset routing (deterministic, rule-based)
- Code-failure repair loop (**max 2 repairs**, deterministic code modifications only)
- Summary groundedness revision loop (**max 1 pass**)

## Not allowed
- Web browsing by default
- Unrestricted shell/filesystem/network access
- Unbounded retries
- Open-ended LLM code generation (only template-based codegen)
- Generic "chat with CSV" as main product

## Sandbox rules
Generated code must run only in isolation:
- No network access (AST import policy enforces this)
- Allowlisted libs only: `csv`, `json`, `math`, `pathlib`, `statistics`, `datetime`, `collections`, `html`, `sys`, `pandas`, `numpy`, `matplotlib`, `seaborn`
- Time / CPU / memory limits (subprocess timeout + POSIX rlimits)
- Run-scoped workspace — generated code can only read/write within its run dir
- Capture stdout / stderr / artifacts
- **Two layers of static analysis before any subprocess spawns:**
  1. AST import policy — rejects any unapproved import
  2. Suspicious-pattern check — rejects `eval`, `exec`, `os.system`, `os.environ`, hardcoded system paths, etc.

## Repair loop rules
On recoverable failure:
- Classify failure type: `missing_column`, `date_parsing`, `chart_error`, `numeric_error`, `generic_runtime`
- Apply targeted repair: modify codegen context (skip charts, remove bad columns, disable date analysis)
- Re-generate code from the same template family
- Re-validate (import policy + suspicious patterns) before re-executing
- Max 2 repair attempts — stop after that
- Do NOT repair: `import_policy`, `syntax_error`, `timeout`, sandbox policy violations

## Groundedness rules
- Every report claim must reference a specific field in `summary.json` or profile
- Claims are classified as `supported | unsupported | uncertain` with a traceable source
- Unsupported claims are removed (not rewritten) — single revision pass only
- The claim list is attached to the report payload for auditability
- No claim is generated without a corresponding computed fact

## Context rules
- Never dump full datasets into model context
- Prefer schema summary, sampled rows, profile stats, artifact metadata
- Keep prompts short, structured, task-specific
- Keep model context lean: schema summary + profiling metadata + sampled rows + relevant logs

## State rules
Persist only what helps execution or recovery:
- run_id
- file metadata (filename, not content)
- profile
- route
- plan
- generated code
- execution logs (stdout, stderr, duration)
- artifacts (SVG charts, summary.json, summary_table.csv)
- report payload
- retry/repair count
- claim list

Do not persist hidden reasoning or unnecessary raw data copies.

## Public API safety rules
- Never expose host filesystem paths in API responses
- `ArtifactMetadata.to_dict()` must omit the internal `path` field
- Validate run_id and artifact ownership on every artifact request
- Return clean 404/410 errors for missing or expired runs/artifacts

## Source of truth
- Read `NORTHSTAR.md` first.
- Work only on the **active phase**.
- Implement only that phase's scope.
- Mark checklist items only when complete and observable.

## Done criteria
A task is done only if:
1. It matches the active phase
2. It passes that phase's acceptance criteria
3. It is visible in code/UI/tests/artifacts
4. `NORTHSTAR.md` is updated accurately

## Repo shape
```
/app          — Next.js UI (upload, workspace, report view)
/backend      — FastAPI API, services, tests
/docs         — Architecture notes
/examples     — Demo datasets (CSV)
/exports      — Placeholder for generated artifacts
/evaluators   — Placeholder (evaluation logic lives in backend/services/)
/prompts      — Placeholder (all prompts are in backend/services/, not separate files)
/sandbox      — Placeholder (sandbox logic lives in backend/services/sandbox_runner.py)
/workflows    — Placeholder (workflow logic lives in backend/services/ and backend/main.py)
/tests        — Top-level test placeholder (actual tests in backend/tests/)
```

Note: `/evaluators`, `/prompts`, `/sandbox`, `/workflows` contain only README
placeholders.  The actual code lives in `backend/services/`.

## Final rule
Build the smallest version that works end to end. Add complexity only when it
measurably improves capability or safety.
