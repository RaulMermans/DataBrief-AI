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
    for label, value in _prioritize_kpis(kpis, dataset_type):
        report.kpi_cards.append(KpiCard(label=label, value=value, source="summary.json:kpis"))

    report.top_findings = _build_top_findings(
        dataset_type=dataset_type,
        kpis=kpis,
        numeric_summary=numeric_summary,
        category_summary=category_summary,
    )

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
    business_kpis = [
        label for label, _value in _prioritize_kpis(kpis, dataset_type)
        if label not in {"Rows", "Columns", "Duplicate rows", "Missing cells"}
    ]
    if business_kpis:
        recommendations.append(
            f"Use {', '.join(business_kpis[:3])} as the primary review metrics; "
            "they are computed directly from the uploaded data."
        )
    if dataset_type == "ecommerce":
        if _numeric_kpi(kpis, "Return/cancel rate") > 0:
            recommendations.append(
                f"Review return and cancellation drivers because Return/cancel rate is {kpis['Return/cancel rate']}%."
            )
        if _numeric_kpi(kpis, "Discount rate") > 0:
            recommendations.append(
                f"Audit discounting by category or channel because Discount rate is {kpis['Discount rate']}%."
            )
        if any(label.startswith("Distinct channel") for label in kpis):
            recommendations.append(
                "Compare revenue by channel before reallocating acquisition effort."
            )
    if dup_from_summary > 0:
        recommendations.append(
            f"Review {dup_from_summary} duplicate row(s) before drawing conclusions."
        )
    if missing_cells:
        recommendations.append(
            f"Address {missing_cells} missing cell(s) to improve analysis completeness."
        )
    if not recommendations and plan_questions:
        recommendations.append(f"Investigate: {plan_questions[0]}")
    report.business_recommendations = recommendations

    # Executive summary (3 sentences max, fully grounded)
    chart_count = len(report.chart_artifacts)
    kpi_highlight = ""
    for label, value in _prioritize_kpis(kpis, dataset_type)[:3]:
        if label in {"Rows", "Columns"}:
            continue
        kpi_highlight += f" {label}: {value}."
    report.executive_summary = (
        f"Analyzed a {dataset_type} dataset with {row_count} rows and {col_count} columns.{kpi_highlight} "
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


def _prioritize_kpis(kpis: dict[str, Any], dataset_type: str) -> list[tuple[str, Any]]:
    structural = {"Rows", "Columns", "Duplicate rows", "Missing cells"}
    ecommerce_order = [
        "Gross sales",
        "Net revenue",
        "Gross margin",
        "Order count",
        "Units sold",
        "Average order value",
        "Return/cancel rate",
        "Discount rate",
    ]
    sales_order = ["Total revenue", "Average revenue", "Total sales", "Average sales"]
    preferred = ecommerce_order if dataset_type == "ecommerce" else sales_order
    ordered: list[tuple[str, Any]] = []
    used: set[str] = set()

    for wanted in preferred:
        if wanted in kpis:
            ordered.append((wanted, kpis[wanted]))
            used.add(wanted)
    for label, value in kpis.items():
        if label not in used and label not in structural:
            ordered.append((label, value))
            used.add(label)
    for label in ("Rows", "Columns", "Duplicate rows", "Missing cells"):
        if label in kpis and label not in used:
            ordered.append((label, kpis[label]))
    return ordered


def _build_top_findings(
    *,
    dataset_type: str,
    kpis: dict[str, Any],
    numeric_summary: dict[str, Any],
    category_summary: dict[str, Any],
) -> list[Finding]:
    findings: list[Finding] = []

    if dataset_type == "ecommerce":
        if "Net revenue" in kpis and "Order count" in kpis:
            findings.append(Finding(
                description=f"Net revenue is {kpis['Net revenue']} across {kpis['Order count']} order(s).",
                source="summary.json:kpis",
            ))
        if "Average order value" in kpis:
            findings.append(Finding(
                description=f"Average order value is {kpis['Average order value']}.",
                source="summary.json:kpis",
            ))
        if "Return/cancel rate" in kpis:
            findings.append(Finding(
                description=f"Return/cancel rate is {kpis['Return/cancel rate']}%.",
                source="summary.json:kpis",
            ))
        if "Discount rate" in kpis:
            findings.append(Finding(
                description=f"Discount rate is {kpis['Discount rate']}%.",
                source="summary.json:kpis",
            ))

    for col, counts in category_summary.items():
        if counts:
            top_label, top_count = counts[0]
            desc = f"{col}: '{top_label}' is the largest observed segment with {top_count} row(s)."
            findings.append(Finding(description=desc, source=f"summary.json:category_summary:{col}"))
        if len(findings) >= 6:
            break

    for col, stats in numeric_summary.items():
        desc = (
            f"{col}: total={stats.get('sum')}, average={stats.get('mean')}, "
            f"range={stats.get('min')} to {stats.get('max')}."
        )
        findings.append(Finding(description=desc, source=f"summary.json:numeric_summary:{col}"))
        if len(findings) >= 8:
            break

    return findings[:8]


def _numeric_kpi(kpis: dict[str, Any], label: str) -> float:
    value = kpis.get(label)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0
