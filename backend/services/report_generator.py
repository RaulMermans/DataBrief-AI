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
    dataset_limitations: list[str] = field(default_factory=list)
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
            "dataset_limitations": self.dataset_limitations,
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
    report.chart_artifacts = _prioritize_chart_artifacts(execution.artifacts, dataset_type)

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
        report.dataset_limitations = [
            "The dataset can support profiling only because generated analysis did not complete.",
            "Computed business KPIs, charts, and recommendations are unavailable for this run.",
        ]
        return report

    # --- Full report path ---
    summary = load_summary_json(execution.artifacts)
    kpis: dict[str, Any] = summary.get("kpis", {})
    numeric_summary: dict[str, Any] = summary.get("numeric_summary", {})
    category_summary: dict[str, Any] = summary.get("category_summary", {})
    dup_from_summary = summary.get("duplicate_rows", dup_rows)

    # KPI cards — skip "Unavailable" sentinel values from primary display;
    # they are surfaced as anomaly rows or limitations instead.
    for label, value in _prioritize_kpis(kpis, dataset_type):
        if value == _UNAVAILABLE:
            continue
        report.kpi_cards.append(KpiCard(label=label, value=value, source="summary.json:kpis"))

    report.top_findings = _build_top_findings(
        dataset_type=dataset_type,
        row_count=row_count,
        kpis=kpis,
        numeric_summary=numeric_summary,
        category_summary=category_summary,
        duplicate_rows=dup_from_summary,
        missing_cells=kpis.get("Missing cells", 0),
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
    # Surface unavailable ecommerce metrics explicitly
    if dataset_type == "ecommerce":
        return_rate_value = kpis.get("Return/cancel rate")
        if return_rate_value == _UNAVAILABLE:
            report.anomaly_table.append(AnomalyRow(
                check="Return/cancel rate",
                value="Unavailable — no return, refund, cancel, or status field detected",
                flag="warning",
            ))
        if "Purchase line count" in kpis:
            report.anomaly_table.append(AnomalyRow(
                check="Order ID",
                value="Not detected — true order count and AOV are unavailable",
                flag="warning",
            ))
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
        return_rate = kpis.get("Return/cancel rate")
        if return_rate is not None and return_rate != _UNAVAILABLE and isinstance(return_rate, (int, float)) and return_rate > 0:
            recommendations.append(
                f"Review return and cancellation drivers because Return/cancel rate is {return_rate}%."
            )
        if _numeric_kpi(kpis, "Discount rate") > 0:
            recommendations.append(
                f"Audit discounting by category or channel because Discount rate is {kpis['Discount rate']}%."
            )
        if any(label.startswith("Distinct channel") for label in kpis):
            recommendations.append(
                "Compare revenue by channel before reallocating acquisition effort."
            )
    concentration = _highest_category_concentration(category_summary, row_count)
    if concentration and concentration[2] >= 60:
        recommendations.append(
            f"Treat segment comparisons cautiously because {concentration[0]} is concentrated in '{concentration[1]}' at {concentration[2]}% of rows."
        )
    if dup_from_summary > 0:
        recommendations.append(
            f"Review {dup_from_summary} duplicate row(s) before drawing conclusions."
        )
    if missing_cells:
        recommendations.append(
            f"Address {missing_cells} missing cell(s) to improve analysis completeness."
        )
    if warnings:
        recommendations.append(
            "Review profile warning(s), including missing or duplicate data quality issues, before sharing conclusions."
        )
    report.business_recommendations = recommendations

    report.dataset_limitations = _build_dataset_limitations(
        dataset_type=dataset_type,
        profile=profile,
        kpis=kpis,
        category_summary=category_summary,
        chart_count=len(report.chart_artifacts),
    )

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

    has_order_id = "Order count" in kpis
    has_return_rate = kpis.get("Return/cancel rate") not in (None, _UNAVAILABLE)
    if has_order_id and has_return_rate:
        data_conf = "High"
        biz_conf = "High"
    elif has_order_id or has_return_rate:
        data_conf = "High"
        biz_conf = "Medium"
    else:
        data_conf = "High"
        biz_conf = "Medium — order-level and return/cancel metrics are unavailable for this dataset"
    report.confidence_note = (
        f"Data confidence: {data_conf}. Business interpretation: {biz_conf}. "
        f"All KPIs, findings, and recommendations are derived from the uploaded file, profile, and summary.json. "
        f"No external data sources or assumptions are used."
    )

    return report


_UNAVAILABLE = "Unavailable"


def _prioritize_kpis(kpis: dict[str, Any], dataset_type: str) -> list[tuple[str, Any]]:
    structural = {"Rows", "Columns", "Duplicate rows", "Missing cells"}
    ecommerce_order = [
        "Gross sales",
        "Net revenue",
        "Total estimated spend",
        "Gross margin",
        "Order count",
        "Purchase line count",
        "Units sold",
        "Average order value",
        "Average spend per row",
        "Average item price",
        "Return/cancel rate",
        "Discount rate",
    ]
    sales_order = [
        "Total revenue",
        "Order count",
        "Purchase line count",
        "Average order value",
        "Average spend per row",
        "New customer count",
        "New customer rate",
        "Average revenue",
        "Total sales",
        "Average sales",
    ]
    finance_order = ["Total amount", "Average amount", "Total debit", "Total credit", "Total balance"]
    if dataset_type == "ecommerce":
        preferred = ecommerce_order
    elif dataset_type == "finance":
        preferred = finance_order
    else:
        preferred = sales_order
    ordered: list[tuple[str, Any]] = []
    used: set[str] = set()

    for wanted in preferred:
        if wanted in kpis:
            ordered.append((wanted, kpis[wanted]))
            used.add(wanted)
    for label, value in kpis.items():
        if label not in used and label not in structural and not _is_identifier_metric(label):
            ordered.append((label, value))
            used.add(label)
    for label in ("Rows", "Columns", "Duplicate rows", "Missing cells"):
        if label in kpis and label not in used:
            ordered.append((label, kpis[label]))
    return ordered


def _build_top_findings(
    *,
    dataset_type: str,
    row_count: int,
    kpis: dict[str, Any],
    numeric_summary: dict[str, Any],
    category_summary: dict[str, Any],
    duplicate_rows: int,
    missing_cells: int,
) -> list[Finding]:
    findings: list[Finding] = []

    if dataset_type == "ecommerce":
        revenue_label = "Net revenue" if "Net revenue" in kpis else "Total estimated spend"
        if revenue_label in kpis and "Order count" in kpis:
            findings.append(Finding(
                description=f"{revenue_label} is {kpis[revenue_label]} across {kpis['Order count']} order(s).",
                source="summary.json:kpis",
            ))
        elif revenue_label in kpis and "Purchase line count" in kpis:
            findings.append(Finding(
                description=f"{revenue_label} is {kpis[revenue_label]} across {kpis['Purchase line count']} purchase line(s). No order ID detected; true order-level metrics are unavailable.",
                source="summary.json:kpis",
            ))
        if "Average order value" in kpis:
            findings.append(Finding(
                description=f"Average order value is {kpis['Average order value']}.",
                source="summary.json:kpis",
            ))
        elif "Average spend per row" in kpis:
            findings.append(Finding(
                description=f"Average spend per purchase line is {kpis['Average spend per row']}. No order ID detected; average order value is unavailable.",
                source="summary.json:kpis",
            ))
        return_rate = kpis.get("Return/cancel rate")
        if return_rate is not None and return_rate != _UNAVAILABLE:
            findings.append(Finding(
                description=f"Return/cancel rate is {return_rate}%.",
                source="summary.json:kpis",
            ))
        if "Discount rate" in kpis:
            findings.append(Finding(
                description=f"Discount rate is {kpis['Discount rate']}%.",
                source="summary.json:kpis",
            ))

    concentration_findings: list[Finding] = []
    for col, counts in category_summary.items():
        if counts:
            top_label, top_count = counts[0]
            share = round((float(top_count) / row_count) * 100, 1) if row_count else 0
            desc = f"{col}: '{top_label}' is the largest observed segment with {top_count} row(s), representing {share}% of the dataset."
            concentration_findings.append(Finding(description=desc, source=f"summary.json:category_summary:{col}"))
    findings.extend(sorted(concentration_findings, key=lambda f: _percent_in_text(f.description), reverse=True))

    for col, stats in numeric_summary.items():
        if _is_identifier_metric(col):
            continue
        if _is_date_column(col):
            continue
        min_value = stats.get("min")
        max_value = stats.get("max")
        mean_value = stats.get("mean")
        desc = (
            f"{col}: total={stats.get('sum')}, average={mean_value}, "
            f"range={min_value} to {max_value}."
        )
        findings.append(Finding(description=desc, source=f"summary.json:numeric_summary:{col}"))
        if len(findings) >= 8:
            break

    if duplicate_rows > 0:
        findings.append(Finding(
            description=f"Data quality risk: {duplicate_rows} duplicate row(s) were detected.",
            source="summary.json:kpis",
        ))
    if missing_cells > 0:
        findings.append(Finding(
            description=f"Data quality risk: {missing_cells} missing cell(s) were detected.",
            source="summary.json:kpis",
        ))

    return findings[:8]


def _numeric_kpi(kpis: dict[str, Any], label: str) -> float:
    value = kpis.get(label)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _prioritize_chart_artifacts(artifacts: list[ArtifactMetadata], dataset_type: str) -> list[str]:
    charts = [a.url for a in artifacts if a.content_type == "image/svg+xml" and a.size_bytes > 0]
    if dataset_type == "ecommerce":
        priority = [
            "revenue_by_category",
            "revenue_by_channel",
            "revenue_by_device",
            "revenue_trend",
            "status_distribution",
            "margin_by",
            "missing_values",
        ]
    elif dataset_type == "finance":
        priority = ["time_", "category_", "histogram_", "missing_values"]
    else:
        priority = ["time_", "category_", "histogram_", "missing_values"]

    def sort_key(url: str) -> tuple[int, str]:
        name = url.split("/")[-1].lower()
        for index, token in enumerate(priority):
            if token in name:
                return (index, name)
        return (len(priority), name)

    return sorted(charts, key=sort_key)[:5]


def _highest_category_concentration(
    category_summary: dict[str, Any], row_count: int
) -> tuple[str, str, float] | None:
    best: tuple[str, str, float] | None = None
    if row_count <= 0:
        return None
    for col, counts in category_summary.items():
        if not counts:
            continue
        label, count = counts[0]
        share = round((float(count) / row_count) * 100, 1)
        if best is None or share > best[2]:
            best = (col, str(label), share)
    return best


def _build_dataset_limitations(
    *,
    dataset_type: str,
    profile: dict[str, Any],
    kpis: dict[str, Any],
    category_summary: dict[str, Any],
    chart_count: int,
) -> list[str]:
    columns = [column.lower() for column in profile.get("inferred_types", {}).keys()]
    semantic = profile.get("semantic_profile", {})
    limitations: list[str] = []
    limitations.extend(semantic.get("limitations", []))
    if dataset_type == "ecommerce":
        if "Net revenue" in kpis or "Total estimated spend" in kpis:
            limitations.append("Supports transaction-level spend and volume analysis from the uploaded fields.")
        missing_fields = []
        if not _has_named_column(columns, ["order"]):
            missing_fields.append("order id")
        if not _has_named_column(columns, ["return", "refund", "cancel", "status"]):
            missing_fields.append("return/cancel status")
        if not _has_named_column(columns, ["channel", "source", "device", "region", "country", "state", "city"]):
            missing_fields.append("channel/device/geography")
        if missing_fields:
            limitations.append(f"Does not fully support {', '.join(missing_fields)} analysis because those fields are missing.")
    elif dataset_type == "finance":
        limitations.append("Supports financial amount summaries by available account, category, and date fields.")
    else:
        limitations.append("Supports structural profiling and summaries for detected numeric and categorical fields.")
    if not category_summary:
        limitations.append("Segment comparisons are limited because no categorical summaries were computed.")
    if chart_count == 0:
        limitations.append("Chart support is limited for this dataset because no useful SVG chart artifact was produced.")
    limitations.append("Does not establish causality or benchmark performance without external reference data.")
    return list(dict.fromkeys(limitations))


def _has_named_column(columns: list[str], tokens: list[str]) -> bool:
    return any(any(token in column for token in tokens) for column in columns)


def _is_identifier_metric(label: str) -> bool:
    text = label.lower()
    return text in {"id", "referencia", "reference"} or any(
        token in text for token in (" id", "id ", "identifier", "referencia", "reference", "asin", "isbn", "sku")
    )


def _is_date_column(label: str) -> bool:
    text = label.lower()
    date_tokens = ("date", "fecha", "created_at", "updated_at", "ordered_at", "purchase_date",
                   "transaction_date", "timestamp", "created", "ordered")
    return any(token in text for token in date_tokens)


def _percent_in_text(text: str) -> float:
    marker = "% of the dataset"
    if marker not in text:
        return 0.0
    try:
        prefix = text.split(marker, 1)[0].rsplit(" ", 1)[-1]
        return float(prefix)
    except ValueError:
        return 0.0
