# **Project Overview**

**DataBrief AI** is a workflow-driven analytics copilot that turns uploaded CSV/XLSX files into a board-ready report with profiling, KPI suggestions, charts, anomaly detection, grounded insights, and downloadable analysis code.

**Resolved setup**

* Target: fullstack web app  
* Stack: single-repo with Next.js frontend, FastAPI backend, Python execution sandbox  
* Repo state: greenfield  
* Data: local filesystem for artifacts, SQLite for lightweight run metadata  
* Deploy: docker-local first  
* License: MIT  
* Sensitivity: PII (EU default); policy owner: Engineering Lead

# **Goals**

* Deliver a polished demo from upload to report export.  
* Reliably ingest CSV/XLSX and surface clear validation errors.  
* Generate grounded KPIs, charts, anomalies, and summaries from computed outputs.  
* Run model-generated Python in a bounded sandbox with visible retries.  
* Keep the workflow legible, testable, and portfolio-worthy.

# **Non-goals**

* No general-purpose chat assistant.  
* No autonomous web browsing or external network access in analysis runs.  
* No database connectors or third-party integrations in V1.  
* No multi-user collaboration, long-term memory, or multi-agent orchestration.  
* No destructive write actions against user data.

# **Domain Constraints**

* Use workflow orchestration, not open-ended agent behavior: profile → route → plan → generate code → execute → evaluate/retry → summarize → export.  
* Treat uploads, model outputs, and generated code as untrusted.  
* Never claim findings, KPIs, or anomalies unless they are backed by execution outputs.  
* Keep model context lean: schema summary, profiling metadata, sampled rows, relevant logs only.  
* Bound retries strictly: max 2 code retries, max 1 summary-grounding revision.  
* Sandbox execution must be offline, resource-limited, package-allowlisted, and file-scoped.  
* When columns are ambiguous, state assumptions and degrade gracefully.  
* Surface data-quality warnings prominently.

# **Codebase Map**

**Repo type:** single-repo

* `app/` — Next.js UI: landing page, workspace, report view, examples, architecture page  
* `backend/` — FastAPI API and services  
* `sandbox/` — bounded Python execution runtime  
* `workflows/` — pipeline orchestration and run state  
* `prompts/` — prompt templates per step  
* `evaluators/` — execution-repair and grounding checks  
* `examples/` — demo datasets  
* `exports/` — generated report/code artifacts  
* `docs/` — architecture notes and demo materials  
* `tests/` — integration and regression tests

**Key entrypoints**

* `app/page.tsx` — landing page  
* `app/workspace/page.tsx` — upload and live workflow view  
* `app/report/[runId]/page.tsx` — final report and exports  
* `backend/main.py` — API entrypoint  
* `workflows/run_pipeline.py` — end-to-end orchestration  
* `sandbox/runner.py` — safe execution runner

# **Run / Test / Build**

\# install  
npm install  
python \-m pip install \-r backend/requirements.txt

\# dev  
npm run dev  
python \-m uvicorn backend.main:app \--reload

\# test  
npm test  
pytest \-q

\# build  
npm run build  
python \-m compileall backend sandbox workflows evaluators

**Conventions**

* Uploaded files remain immutable after validation.  
* Artifacts are stored per `run_id`.  
* Metadata storage stays lightweight.  
* Schema changes use reversible migrations under `migrations/`.

# **Collaboration & Change Workflow**

* Keep changes small, reviewable, and tied to one workflow step or UI slice.  
* Use Conventional Commits.  
* Work in this order: plan → minimal diff → tests → impact check → docs update.

**Before acting**

* Read the relevant workflow step and adjacent state/evaluator logic.  
* List touched files and keep the set minimal.  
* Define verification before implementing.

**Implementation rules**

* Preserve explicit stage boundaries and typed run-state contracts.  
* Avoid hidden coupling between UI state and orchestration state.  
* Add logs that make routing, retries, and grounding decisions inspectable.  
* Do not add heavy frameworks unless they clearly reduce complexity.

# **Security & Privacy**

* Never commit secrets; use `.env` and maintain `.env.example`.  
* Treat uploads, model outputs, and execution traces as untrusted.  
* Redact obvious PII in previews, logs, and exported demo artifacts where feasible.  
* Keep the sandbox offline, allowlisted, resource-bounded, and scoped to the current run.  
* Do not send full datasets to the model when summaries or aggregates are enough.  
* Never report unsupported claims.  
* Include a confidence/data-quality note in user-facing reports.  
* Minimize retention of sensitive rows; prefer derived summaries over raw persistence.

# **Assumptions**

* Single-repo architecture.  
* Greenfield implementation.  
* Next.js \+ FastAPI \+ Python sandbox.  
* SQLite is sufficient for MVP metadata.  
* Docker-local is the initial deployment target.  
* MIT license.  
* PII-sensitive by default because uploaded spreadsheets may contain customer, employee, or financial identifiers.  
* Coverage target: 80% line coverage.  
* LangGraph is optional and only justified if it improves retry/checkpoint clarity.  
* Priority is the simplest reliable end-to-end flow, not agent complexity.

