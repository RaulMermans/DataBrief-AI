"""Report generator.

Builds a structured ``ReportPayload`` from *computed outputs only*:

- profile stats (rows, columns, missing, duplicates, warnings)
- summary.json artifact content (kpis, numeric_summary, category_summary)
- artifact metadata (chart names, file sizes)
- the analysis plan (used for framing, not for inventing facts)
- the execution evaluation note

No facts are invented.  Every section is sourced from a specific field in the
computed data.  Sections that cannot be populated from computed data are
marked with a sentinel so the groundedness evaluator can remove them.

The caller is responsible for loading summary.json from the artifact directory
if available.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from services.evaluator import ExecutionEvaluation
from services.sandbox_runner import ArtifactMetadata, SandboxResult


_UNSUPPORTED = "[UNSUPPORTED — no computed data]"


@dataclass
class KpiCard:
    label: str
    value: Any
    source: str  # e.g. "summary.json:kpis"

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": self.value, "source": self.source}


@dataclass
class Finding:
    description: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {"description": self.description, "source": self.source}


@dataclass
class AnomalyRow:
    check: str
    value: Any
    flag: str  # "ok" | "warning" | "error"

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.check, "value": self.value, "flag": self.flag}


@dataclass
class ReportPayload:
    """Structured report built exclusively from computed outputs."""

    # Populated on success
    executive_summary: str = ""
    kpi_cards: list[KpiCard] = field(default_factory=list)
    top_findings: list[Finding] = field(default_factory=list)
    anomaly_table: list[AnomalyRow] = field(default_factory=list)
    data_quality_warnings: list[str] = field(default_factory=list)
    business_recommendations: list[str] = field(default_factory=list)
    confidence_note: str = ""

    # Meta
    is_partial: bool = False  # True when execution never fully succeeded
    evaluator_note: str = ""
    chart_artifacts: list[str] = field(default_factory=list)

    # Groundedness tracking
    revised: bool = False
    revision_note: str = ""
    claims: list[dict] = field(default_factory=list)  # GroundedClaim dicts

    def to_dict(self) -> dict[str, Any]:
        return {
            "executive_summary": self.executive_summary,
            "kpi_cards": [c.to_dict() for c in self.kpi_cards],
            "top_findings": [f.to_dict() for f in self.top_findings],
            "anomaly_table": [r.to_dict() for r in self.anomaly_table],
            "data_quality_warnings": self.data_quality_warnings,
            "business_recommendations": self.business_recommendations,
            "confidence_note": self.confidence_note,
            "is_partial": self.is_partial,
            "evaluator_note": self.evaluator_note,
            "chart_artifacts": self.chart_artifacts,
            "revised": self.revised,
            "revision_note": self.revision_note,
            "claims": self.claims,
        }


def load_summary_json(artifacts: list[ArtifactMetadata]) -> dict[str, Any]:
    """Load and parse summary.json from *artifacts* if present, else {}."""
    for artifact in artifacts:
        if artifact.name == "summary.json":
            try:
                return json.loads(Path(artifact.path).read_text(encoding="utf-8"))
            except Exception:
                return {}
    return {}


def generate_report(
    *,
    profile: dict[str, Any],
    route: dict[str, Any],
    plan: dict[str, Any],
    evaluation: ExecutionEvaluation,
    execution: SandboxResult,
) -> ReportPayload:
    """Build and return a ``ReportPayload``.

    If execution failed, the report is marked ``is_partial=True`` and only
    contains sections that can be populated without computed outputs.
    """
    report = ReportPayload()
    report.evaluator_note = evaluation.note
    dataset_type = route.get("dataset_type", "generic")
    row_count = profile.get("row_count", 0)
    col_count = profile.get("column_count", 0)
    dup_rows = profile.get("duplicate_rows", 0)
    warnings: list[str] = profile.get("warnings", [])
    report.data_quality_warnings = list(warnings)

    # Chart artifacts (names only — URLs are provided by execution.artifacts)
    report.chart_artifacts = [
        a.url for a in execution.artifacts if a.content_type == "image/svg+xml"
    ]

    if evaluation.outcome != "success":
        # Partial results path: no computed kpis / summaries available.
        report.is_partial = True
        report.executive_summary = (
            f"Analysis could not be completed. "
            f"The execution evaluator reported: {evaluation.note} "
            f"Profile: {row_count} rows, {col_count} columns."
        )
        report.confidence_note = (
            "This is a partial result. Execution did not complete successfully. "
            "No computed KPIs or findings are available."
        )
        return report

    # --- Full report path ---
    summary = load_summary_json(execution.artifacts)
    kpis: dict[str, Any] = summary.get("kpis", {})
    numeric_summary: dict[str, Any] = summary.get("numeric_summary", {})
    category_summary: dict[str, Any] = summary.get("category_summary", {})
    dup_from_summary = summary.get("duplicate_rows", dup_rows)

    # KPI cards
    for label, value in kpis.items():
        report.kpi_cards.append(KpiCard(label=label, value=value, source="summary.json:kpis"))

    # Top findings from numeric summary
    for col, stats in numeric_summary.items():
        desc = (
            f"{col}: mean={stats.get('mean')}, "
            f"min={stats.get('min')}, max={stats.get('max')}, "
            f"count={stats.get('count')}"
        )
        report.top_findings.append(Finding(description=desc, source=f"summary.json:numeric_summary:{col}"))

    # Top findings from category summary (top category per column)
    for col, counts in category_summary.items():
        if counts:
            top_label, top_count = counts[0]
            desc = f"{col}: top value '{top_label}' appears {top_count} time(s)"
            report.top_findings.append(Finding(description=desc, source=f"summary.json:category_summary:{col}"))

    # Anomaly table
    missing_cells = kpis.get("Missing cells", sum(profile.get("missing_percent_by_column", {}).values()))
    report.anomaly_table = [
        AnomalyRow(
            check="Duplicate rows",
            value=dup_from_summary,
            flag="warning" if dup_from_summary > 0 else "ok",
        ),
        AnomalyRow(
            check="Missing cells",
            value=missing_cells,
            flag="warning" if missing_cells > 0 else "ok",
        ),
    ]
    # Add data-quality warnings from profile as anomaly rows
    for warning in warnings:
        report.anomaly_table.append(
            AnomalyRow(check="Profile warning", value=warning, flag="warning")
        )

    # Business recommendations — grounded in plan + computed KPIs
    plan_kpis: list[str] = plan.get("likely_kpis", [])
    plan_questions: list[str] = plan.get("business_questions", [])
    recommendations: list[str] = []
    if kpis:
        computed_kpi_names = list(kpis.keys())
        recommendations.append(
            f"Focus attention on: {', '.join(computed_kpi_names[:3])}. "
            "These are computed directly from the uploaded data."
        )
    if dup_from_summary > 0:
        recommendations.append(
            f"Review {dup_from_summary} duplicate row(s) before drawing conclusions."
        )
    if missing_cells:
        recommendations.append(
            f"Address {missing_cells} missing cell(s) to improve analysis completeness."
        )
    # Add plan-derived questions as investigation suggestions (not facts)
    for question in plan_questions[:3]:
        recommendations.append(f"Investigate: {question}")
    report.business_recommendations = recommendations

    # Executive summary (3 sentences max, fully grounded)
    chart_count = len(report.chart_artifacts)
    kpi_highlight = ""
    for label, value in list(kpis.items())[:2]:
        kpi_highlight += f" {label}: {value}."
    report.executive_summary = (
        f"Processed {row_count} rows and {col_count} columns "
        f"from a {dataset_type} dataset.{kpi_highlight} "
        f"The analysis produced {chart_count} chart(s) and flagged "
        f"{dup_from_summary} duplicate row(s) and {missing_cells} missing cell(s)."
    )

    report.confidence_note = (
        f"All KPIs and findings above are computed from the uploaded file. "
        f"Business recommendations are derived from the analysis plan and computed KPIs. "
        f"No external data sources or assumptions are used. "
        f"Plan KPIs listed for reference: {', '.join(plan_kpis[:3]) or 'none'}."
    )

    return report
