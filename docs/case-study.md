# DataBrief AI — Bounded AI Analytics Workflow

## Problem

Business teams regularly receive spreadsheets from stakeholders and need fast, credible summaries: what are the key metrics, what is the data quality like, are there obvious anomalies, and what should they investigate further?

Manual analysis is slow and inconsistent. Generic AI chatbots produce hallucinated claims and unsupported metrics when given raw CSVs. The challenge is to automate analytics in a way that is **fast, trustworthy, and safe** — with clearly stated limitations.

## Solution

DataBrief AI is a bounded AI analytics workflow that transforms CSV/XLSX files into structured business reports through:

1. Deterministic dataset profiling
2. Domain routing (sales, ecommerce, finance, generic)
3. Template-based Python code generation
4. Bounded sandbox execution
5. Evaluation and controlled repair loops
6. Grounded report generation from computed outputs only

No fact is invented. Every KPI, finding, and recommendation is sourced from the uploaded file.

## Architecture

```
Upload → Validate → Profile → Route → Plan → Execute → Evaluate → Repair → Report → Export
```

| Stage | What it does |
|---|---|
| Upload & Validate | Accepts CSV/XLSX; rejects malformed files with clear errors |
| Profile | Detects column types, missing values, duplicates, and semantic roles |
| Route | Classifies dataset as sales, ecommerce, finance, or generic |
| Plan | Generates a deterministic analysis plan: KPIs, questions, charts |
| Execute | Runs template-generated Python in a bounded, allowlisted sandbox |
| Evaluate | Assesses whether execution succeeded or needs repair |
| Repair | Up to 2 bounded attempts to fix recoverable failures |
| Report | Builds structured report from computed outputs only |
| Export | Produces downloadable report (Markdown), findings (JSON), and analysis script (Python) |

## Key Features

- **Grounded outputs** — KPIs, findings, and recommendations reference only what was computed from the uploaded data
- **Semantic column detection** — Distinguishes identifiers, dates, revenue, quantity, price, status, and geography columns
- **Safe label handling** — Date columns are never treated as numeric KPIs; identifier columns are never quantified; missing fields produce "Unavailable" notices rather than false zeros
- **Bounded repair** — Up to 2 repair attempts for recoverable execution failures; unrecoverable errors surface clearly
- **Honest confidence** — Confidence reflects available data signals; business interpretation is labeled Medium when critical fields are absent
- **Export-ready** — Full report, findings JSON, and the generated Python script are downloadable for every run

## Workflow vs Agent Decision

This project intentionally uses a bounded workflow instead of a fully autonomous agent. The reasons:

**Why workflow:**
- Spreadsheet analysis has a predictable, repeatable structure
- Deterministic profiling and routing eliminate ambiguity before code generation
- Bounded execution with an allowlist prevents unexpected behavior
- Groundedness checks ensure no unsupported claims reach the report
- Retry limits and partial-result surfacing make failures understandable

**Why not autonomous agent:**
- Open-ended agents can generate hallucinated KPIs from thin evidence
- Autonomous tool use in a financial context requires stricter accountability
- Users need to understand and trust each output claim
- Agent architectures add complexity without clear benefit for this well-structured task

## Current Limitations

- **No order-level metrics without an order ID** — True order count and average order value require an order ID column; without one, the workflow uses "purchase line count" and flags the limitation explicitly
- **Return/cancel rate requires a status field** — Without a return, refund, cancel, or status column, the metric is labeled "Unavailable"
- **Sandbox is statically gated, not OS-isolated** — Import policy is enforced via AST analysis; OS-level network isolation is not implemented
- **Single-run, no memory** — Each upload is independent; there is no cross-run analysis or session persistence
- **File size cap** — Demo deployment caps uploads at 5 MB; large files require local deployment
- **No streaming** — Results appear only after the full pipeline completes

## Future Improvements

- True OS-level sandbox isolation (Docker or seccomp)
- Streaming workflow status to the frontend
- Persistent run history for multi-upload comparison
- User-configurable analysis focus (e.g., "focus on geographic breakdown")
- Support for multi-sheet XLSX files
- Scheduled re-analysis for regularly updated datasets
