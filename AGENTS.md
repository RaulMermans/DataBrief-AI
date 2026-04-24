# AGENTS.md

## Product
DataBrief AI = workflow-driven analytics copilot for CSV/XLSX uploads.
Output: profile, plan, Python analysis, sandboxed execution, grounded report, exports.

## Build mode
- Build a **workflow**, not a general autonomous agent.
- Keep steps deterministic unless bounded agentic behavior clearly helps.
- Optimize for reliability, legibility, and demo quality.

## Core flow
`validate -> profile -> route -> plan -> codegen -> execute -> evaluate -> summarize -> export`

## Allowed agentic behavior
- dataset routing
- code-failure retry loop (**max 2**)
- summary revision loop (**max 1**)

## Not allowed
- web browsing by default
- unrestricted shell/filesystem/network access
- unbounded retries
- scope beyond active phase
- generic “chat with CSV” as main product

## Sandbox rules
Generated code must run only in isolation:
- no network
- allowlisted libs only
- time / CPU / memory limits
- run-scoped workspace
- capture stdout / stderr / artifacts

## Context rules
- never dump full datasets into model context unless required
- prefer schema summary, sampled rows, profile stats, artifact metadata
- keep prompts short, structured, task-specific

## State rules
Persist only what helps execution or recovery:
- run_id
- file metadata
- profile
- route
- plan
- code versions
- execution logs
- artifacts
- report payload
- retry count

Do not persist hidden reasoning or unnecessary raw data copies.

## Source of truth
- Read `NORTHSTAR.md` first.
- Work only on the **active phase**.
- Implement only that phase’s scope.
- Mark checklist items only when complete and observable.

## Done criteria
A task is done only if:
1. it matches the active phase
2. it passes that phase’s acceptance criteria
3. it is visible in code/UI/tests/artifacts
4. `NORTHSTAR.md` is updated accurately

## Repo shape
Preferred:
- `/app`
- `/backend`
- `/sandbox`
- `/workflows`
- `/prompts`
- `/evaluators`
- `/examples`
- `/exports`
- `/tests`
- `/docs`

## Final rule
Build the smallest version that works end to end. Add complexity only when it measurably improves capability or safety.

