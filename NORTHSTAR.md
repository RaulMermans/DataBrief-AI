# NORTHSTAR.md

## Purpose
Roadmap + verification file for DataBrief AI.
Coding agents should read only the active phase, implement that scope, verify against that phase, then update status/checks.

## Update rules
Only edit:
- `Current active phase`
- the active phase `Status`
- that phase checklist
- `Progress log`

## Status values
- `NOT_STARTED`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

## North star
Ship a portfolio-grade analytics copilot that:
- accepts CSV/XLSX
- profiles and classifies data
- plans analysis
- generates Python
- runs it in a sandbox
- recovers from common failures
- produces grounded charts, findings, recommendations, and exports

Stay a **bounded workflow**, not an open-ended agent.

## Principles
- workflow first
- grounded outputs
- bounded retries
- safe execution
- small-context design
- observable system
- demoable in under 2 minutes

## Current active phase
**PHASE_5_EVALUATION_AND_REPORTING**

## Phase index
- `PHASE_1_FOUNDATION`
- `PHASE_2_UPLOAD_AND_PROFILING`
- `PHASE_3_ROUTING_AND_PLANNING`
- `PHASE_4_CODEGEN_AND_SANDBOX`
- `PHASE_5_EVALUATION_AND_REPORTING`
- `PHASE_6_EXPORTS_AND_POLISH`
- `PHASE_7_HARDENING_AND_SHOWCASE`

---

# PHASE_1_FOUNDATION
**Status:** DONE

## Scope
- repo structure
- frontend shell
- backend shell
- workflow placeholder
- sandbox placeholder
- examples/tests/docs dirs
- config/env template
- basic README
- landing page
- health route

## Acceptance criteria
- app starts locally
- frontend/backend boundaries are clear
- landing page exists
- health route works
- startup verification exists

## Checklist
- [x] repo structure
- [x] frontend shell
- [x] backend shell
- [x] workflow placeholder
- [x] sandbox placeholder
- [x] examples/tests/docs
- [x] config/env template
- [x] README
- [x] landing page
- [x] health route
- [x] startup verified

---

# PHASE_2_UPLOAD_AND_PROFILING
**Status:** DONE

## Scope
- CSV/XLSX upload
- file validation
- dataframe parsing
- dataset profile
- profile UI

## Acceptance criteria
- CSV and XLSX both work
- bad files fail clearly
- UI shows rows, cols, types, missing values, duplicates, sample rows
- at least one profiling test exists

## Checklist
- [x] upload UI
- [x] file validation
- [x] CSV parse
- [x] XLSX parse
- [x] profiling function
- [x] profile UI
- [x] invalid-file errors
- [x] profiling test
- [x] sample verification

## Progress log
- 2026-04-24: Built first CSV-only vertical slice: Next.js upload UI, FastAPI upload endpoint, profiler, sales/generic router, profile/report shell, health route, env validation, and focused backend tests.
- 2026-04-24: Closed ingestion milestone with XLSX support, clearer file validation, sample datasets, and sample route verification.

---

# PHASE_3_ROUTING_AND_PLANNING
**Status:** DONE

## Scope
- classify dataset as sales / generic
- select domain template
- generate structured analysis plan
- render plan

## Acceptance criteria
- at least 3 sample datasets route sensibly
- route is visible in UI or logs
- plan is structured
- full raw dataset is not dumped into context
- at least one routing test exists

## Checklist
- [x] dataset router
- [x] domain templates
- [x] analysis plan
- [x] plan UI
- [x] route logging
- [x] routing test
- [x] sample verification

## Progress log
- 2026-04-24: Started Phase 3 with deterministic sales/generic planning and developer JSON output. Keep next work scoped to planning polish before codegen/sandbox.

---

# PHASE_4_CODEGEN_AND_SANDBOX
**Status:** DONE

## Scope
- code generation
- isolated Python execution
- allowlisted libs
- resource limits
- artifact capture
- execution logs

## Acceptance criteria
- generated code does not run in app server process ✓
- import policy is enforced (AST-based, pre-execution; disallowed modules rejected with a clear structured error) ✓
- network note: network is NOT blocked at the OS level (no network namespace/seccomp); the defence is the AST import policy — socket, urllib, requests, httpx are not on the approved import list and are rejected before the subprocess starts ✓
- success and failure outputs are captured ✓
- good dataset produces at least one chart artifact ✓
- bad generation path fails safely ✓

## Checklist
- [x] code generator
- [x] isolated runtime (subprocess, `-I` flag)
- [x] library allowlist (AST-based pre-execution validation replacing brittle runtime monkeypatch)
- [x] time/memory limits
- [x] stdout/stderr capture
- [x] artifact saving
- [x] code/log UI or debug view
- [x] safe-failure verification

## Progress log
- 2026-04-24: Added deterministic template-based Python generation, bounded subprocess execution, structured logs, artifact capture/serving, debug UI, and Phase 4 backend tests.
- 2026-04-25: Repaired Phase 4 honestly. Replaced brittle `builtins.__import__` monkeypatch (which broke on stdlib internal lazy imports like `_io`) with AST-based pre-execution import validation in `sandbox_runner.validate_imports`. Documented that network is not blocked at OS level — primary defence is the AST import policy. Added 5 new targeted tests (19 total, all passing).

---

# PHASE_5_EVALUATION_AND_REPORTING
**Status:** NOT_STARTED

## Scope
- execution evaluator
- bounded retry loop
- report generator
- groundedness evaluator
- one-pass summary revision

## Acceptance criteria
- code retries max at 2
- summary revision max at 1
- unsupported claims are rejected or revised
- computed findings and recommendations are distinct
- partial results appear if retries are exhausted
- evaluator outcomes are logged or visible

## Checklist
- [ ] execution evaluator
- [ ] code retry loop
- [ ] report generator
- [ ] groundedness evaluator
- [ ] summary revision
- [ ] final report UI
- [ ] partial-result path
- [ ] evaluator logging

---

# PHASE_6_EXPORTS_AND_POLISH
**Status:** NOT_STARTED

## Scope
- report export
- JSON findings export
- Python script export
- better visuals
- progress UI
- better error copy
- sample demo flow

## Acceptance criteria
- at least 3 export types
- UI is polished and demoable
- progress is visible during runs
- demo datasets work reliably
- error states are understandable

## Checklist
- [ ] report export
- [ ] JSON export
- [ ] Python export
- [ ] visual polish
- [ ] progress UI
- [ ] improved errors
- [ ] demo flow

---

# PHASE_7_HARDENING_AND_SHOWCASE
**Status:** NOT_STARTED

## Scope
- tests and eval fixtures
- debug panel
- architecture diagram
- strong README
- screenshots/GIFs
- demo script

## Acceptance criteria
- README explains workflow vs agent choice
- tests cover key steps
- at least 3 demo datasets bundled
- architecture is understandable without chat context
- project demos in under 2 minutes

## Checklist
- [ ] architecture diagram
- [ ] README upgrade
- [ ] eval fixtures
- [ ] debug panel
- [ ] screenshots/GIFs
- [ ] demo script
- [ ] 2-minute demo verified

---

## Progress log
- 2026-04-23 — NORTHSTAR initialized.

## Reminder for coding agents
Read only the active phase by default. Build that phase. Verify that phase. Update that phase.
