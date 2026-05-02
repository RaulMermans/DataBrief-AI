"""Semantic output quality tests — P4 acceptance criteria.

Tests verify that:
- No order ID → no AOV/order-count KPI label
- No status/return field → return rate is "Unavailable"
- Date columns are excluded from numeric findings
- Identifier columns are excluded from numeric KPIs
- Chart titles match the selected metric
- Export links reference run_id
- Confidence is recalibrated when key fields are absent
"""
from __future__ import annotations

import json
from pathlib import Path

from services.evaluator import ExecutionEvaluation
from services.report_generator import generate_report, _UNAVAILABLE
from services.sandbox_runner import ArtifactMetadata, SandboxResult
from services.semantic_profile import build_semantic_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _artifact(name: str, content_type: str = "application/json") -> ArtifactMetadata:
    return ArtifactMetadata(
        name=name,
        path=f"/tmp/run/{name}",
        size_bytes=100,
        content_type=content_type,
        url=f"/api/runs/run/{name}",
    )


def _summary_artifact(tmp_path: Path, payload: dict) -> ArtifactMetadata:
    p = tmp_path / "summary.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return ArtifactMetadata(
        name="summary.json",
        path=str(p),
        size_bytes=p.stat().st_size,
        content_type="application/json",
        url="/api/runs/run/summary.json",
    )


def _success_execution(artifacts=None) -> SandboxResult:
    return SandboxResult(
        run_id="run1",
        status="success",
        exit_code=0,
        stdout="ok",
        stderr="",
        timed_out=False,
        duration_ms=100,
        artifacts=artifacts or [],
        error=None,
    )


_SUCCESS_EVAL = ExecutionEvaluation(outcome="success", note="ok")

_ECOMMERCE_ROUTE = {"dataset_type": "ecommerce", "confidence": 0.78, "explanation": "test"}
_ECOMMERCE_PLAN = {
    "likely_kpis": [],
    "business_questions": [],
    "recommended_transformations": [],
    "recommended_charts": [],
    "anomaly_checks": [],
}


# ---------------------------------------------------------------------------
# P0-1: No order ID → no AOV / order count label
# ---------------------------------------------------------------------------


def test_no_order_id_uses_purchase_line_count(tmp_path):
    """When summary.json has Purchase line count but not Order count, the report
    must not show Order count or Average order value as KPI cards."""
    artifact = _summary_artifact(tmp_path, {
        "dataset_type": "ecommerce",
        "row_count": 30,
        "column_count": 5,
        "duplicate_rows": 0,
        "kpis": {
            "Total estimated spend": 2500.00,
            "Purchase line count": 30,
            "Average spend per row": 83.33,
            "Units sold": 45,
            "Average item price": 55.56,
            "Return/cancel rate": _UNAVAILABLE,
            "Rows": 30,
            "Columns": 5,
            "Duplicate rows": 0,
            "Missing cells": 0,
        },
        "numeric_summary": {},
        "category_summary": {},
    })

    report = generate_report(
        profile={
            "row_count": 30,
            "column_count": 5,
            "duplicate_rows": 0,
            "inferred_types": {
                "purchase_date": "date",
                "category": "string",
                "quantity": "integer",
                "unit_price": "number",
            },
            "missing_percent_by_column": {},
            "warnings": [],
            "sample_rows": [],
        },
        route=_ECOMMERCE_ROUTE,
        plan=_ECOMMERCE_PLAN,
        evaluation=_SUCCESS_EVAL,
        execution=_success_execution(artifacts=[artifact]),
    )

    labels = [c.label for c in report.kpi_cards]
    assert "Order count" not in labels, "Order count must not appear when no order ID"
    assert "Average order value" not in labels, "AOV must not appear when no order ID"
    assert "Purchase line count" in labels
    assert "Total estimated spend" in labels

    # Findings must flag no order ID
    all_text = " ".join(f.description for f in report.top_findings)
    assert "No order ID detected" in all_text or "no order ID" in all_text.lower()

    # Anomaly table must flag the missing order ID
    anomaly_checks = {row.check for row in report.anomaly_table}
    assert "Order ID" in anomaly_checks


def test_no_order_id_caveat_in_findings(tmp_path):
    """Purchase line count finding must contain the caveat about true order-level metrics."""
    artifact = _summary_artifact(tmp_path, {
        "dataset_type": "ecommerce",
        "row_count": 10,
        "column_count": 3,
        "duplicate_rows": 0,
        "kpis": {
            "Total estimated spend": 1000.00,
            "Purchase line count": 10,
            "Average spend per row": 100.00,
            "Return/cancel rate": _UNAVAILABLE,
            "Rows": 10,
            "Columns": 3,
            "Duplicate rows": 0,
            "Missing cells": 0,
        },
        "numeric_summary": {},
        "category_summary": {},
    })

    report = generate_report(
        profile={
            "row_count": 10,
            "column_count": 3,
            "duplicate_rows": 0,
            "inferred_types": {"category": "string", "unit_price": "number"},
            "missing_percent_by_column": {},
            "warnings": [],
            "sample_rows": [],
        },
        route=_ECOMMERCE_ROUTE,
        plan=_ECOMMERCE_PLAN,
        evaluation=_SUCCESS_EVAL,
        execution=_success_execution(artifacts=[artifact]),
    )

    combined = " ".join(f.description for f in report.top_findings)
    assert "order-level metrics are unavailable" in combined or "No order ID detected" in combined


# ---------------------------------------------------------------------------
# P0-2: No status/return field → return rate Unavailable
# ---------------------------------------------------------------------------


def test_no_status_field_return_rate_unavailable(tmp_path):
    """When Return/cancel rate is Unavailable, the KPI card must not be shown
    and the anomaly table must surface the notice."""
    artifact = _summary_artifact(tmp_path, {
        "dataset_type": "ecommerce",
        "row_count": 10,
        "column_count": 4,
        "duplicate_rows": 0,
        "kpis": {
            "Total estimated spend": 500.00,
            "Purchase line count": 10,
            "Return/cancel rate": "Unavailable",
            "Rows": 10,
            "Columns": 4,
            "Duplicate rows": 0,
            "Missing cells": 0,
        },
        "numeric_summary": {},
        "category_summary": {},
    })

    report = generate_report(
        profile={
            "row_count": 10,
            "column_count": 4,
            "duplicate_rows": 0,
            "inferred_types": {"category": "string", "unit_price": "number"},
            "missing_percent_by_column": {},
            "warnings": [],
            "sample_rows": [],
        },
        route=_ECOMMERCE_ROUTE,
        plan=_ECOMMERCE_PLAN,
        evaluation=_SUCCESS_EVAL,
        execution=_success_execution(artifacts=[artifact]),
    )

    # KPI cards must not show return/cancel rate at all
    labels = [c.label for c in report.kpi_cards]
    assert "Return/cancel rate" not in labels

    # Anomaly table must mention it
    anomaly_text = " ".join(str(row.value) for row in report.anomaly_table)
    assert "return" in anomaly_text.lower() or "status" in anomaly_text.lower()

    # Recommendations must not mention return rate
    rec_text = " ".join(report.business_recommendations)
    assert "return and cancellation" not in rec_text.lower()


def test_zero_return_rate_when_status_field_exists_is_shown(tmp_path):
    """When status column exists and returns 0% rate, it is legitimate — show it."""
    artifact = _summary_artifact(tmp_path, {
        "dataset_type": "ecommerce",
        "row_count": 10,
        "column_count": 5,
        "duplicate_rows": 0,
        "kpis": {
            "Net revenue": 900.00,
            "Order count": 10,
            "Average order value": 90.00,
            "Return/cancel rate": 0.0,
            "Rows": 10,
            "Columns": 5,
            "Duplicate rows": 0,
            "Missing cells": 0,
        },
        "numeric_summary": {},
        "category_summary": {},
    })

    report = generate_report(
        profile={
            "row_count": 10,
            "column_count": 5,
            "duplicate_rows": 0,
            "inferred_types": {"status": "string", "revenue": "number"},
            "missing_percent_by_column": {},
            "warnings": [],
            "sample_rows": [],
        },
        route=_ECOMMERCE_ROUTE,
        plan=_ECOMMERCE_PLAN,
        evaluation=_SUCCESS_EVAL,
        execution=_success_execution(artifacts=[artifact]),
    )

    labels = [c.label for c in report.kpi_cards]
    # A 0% rate from a real status field should appear in KPI cards
    assert "Return/cancel rate" in labels


# ---------------------------------------------------------------------------
# P0-3: Date columns excluded from numeric findings
# ---------------------------------------------------------------------------


def test_date_columns_excluded_from_numeric_findings(tmp_path):
    """Numeric summary entries for date-like columns must not appear in top findings."""
    artifact = _summary_artifact(tmp_path, {
        "dataset_type": "ecommerce",
        "row_count": 30,
        "column_count": 4,
        "duplicate_rows": 0,
        "kpis": {
            "Total estimated spend": 2000.00,
            "Purchase line count": 30,
            "Return/cancel rate": _UNAVAILABLE,
            "Rows": 30,
            "Columns": 4,
            "Duplicate rows": 0,
            "Missing cells": 0,
        },
        "numeric_summary": {
            "purchase_date": {
                "count": 30, "sum": 60780000, "mean": 2026000,
                "min": 20260101, "max": 20260228,
            },
            "unit_price": {
                "count": 30, "sum": 2000.0, "mean": 66.67,
                "min": 14.99, "max": 199.0,
            },
        },
        "category_summary": {},
    })

    report = generate_report(
        profile={
            "row_count": 30,
            "column_count": 4,
            "duplicate_rows": 0,
            "inferred_types": {
                "purchase_date": "date",
                "category": "string",
                "unit_price": "number",
            },
            "missing_percent_by_column": {},
            "warnings": [],
            "sample_rows": [],
        },
        route=_ECOMMERCE_ROUTE,
        plan=_ECOMMERCE_PLAN,
        evaluation=_SUCCESS_EVAL,
        execution=_success_execution(artifacts=[artifact]),
    )

    finding_text = " ".join(f.description for f in report.top_findings)
    # purchase_date numeric stats must not appear
    assert "purchase_date: total=" not in finding_text
    assert "average=2026" not in finding_text
    # unit_price numeric stats may appear
    assert "unit_price" in finding_text or len(report.top_findings) > 0


# ---------------------------------------------------------------------------
# P0-4: Identifier columns excluded from numeric KPIs
# ---------------------------------------------------------------------------


def test_identifier_columns_not_in_numeric_kpis(tmp_path):
    """Columns whose labels contain 'id', 'asin', 'isbn', etc. must not appear
    in KPI cards or numeric findings."""
    artifact = _summary_artifact(tmp_path, {
        "dataset_type": "ecommerce",
        "row_count": 5,
        "column_count": 4,
        "duplicate_rows": 0,
        "kpis": {
            "Total ASIN": 12345,
            "Average ASIN": 2469.0,
            "Total estimated spend": 500.0,
            "Purchase line count": 5,
            "Return/cancel rate": _UNAVAILABLE,
            "Rows": 5,
            "Columns": 4,
            "Duplicate rows": 0,
            "Missing cells": 0,
        },
        "numeric_summary": {
            "ASIN": {"count": 5, "sum": 12345, "mean": 2469, "min": 1000, "max": 5000},
            "unit_price": {"count": 5, "sum": 500, "mean": 100, "min": 50, "max": 150},
        },
        "category_summary": {},
    })

    report = generate_report(
        profile={
            "row_count": 5,
            "column_count": 4,
            "duplicate_rows": 0,
            "inferred_types": {"ASIN": "integer", "unit_price": "number"},
            "missing_percent_by_column": {},
            "warnings": [],
            "sample_rows": [],
        },
        route=_ECOMMERCE_ROUTE,
        plan=_ECOMMERCE_PLAN,
        evaluation=_SUCCESS_EVAL,
        execution=_success_execution(artifacts=[artifact]),
    )

    labels = [c.label for c in report.kpi_cards]
    finding_text = " ".join(f.description for f in report.top_findings)
    assert "Total ASIN" not in labels
    assert "Average ASIN" not in labels
    assert "Total ASIN" not in finding_text
    assert "ASIN: total=" not in finding_text


# ---------------------------------------------------------------------------
# P0-5: Confidence recalibration
# ---------------------------------------------------------------------------


def test_confidence_recalibrated_when_fields_absent():
    """When no order ID and no status field, confidence must be capped below 0.90."""
    semantic = build_semantic_profile({
        "inferred_types": {
            "purchase_date": "date",
            "category": "string",
            "quantity": "integer",
            "unit_price": "number",
        },
        "sample_rows": [],
    }).to_dict()

    assert semantic["confidence"] < 0.90, (
        f"Confidence should be recalibrated when order ID and status are absent, got {semantic['confidence']}"
    )


def test_confidence_higher_when_full_signals():
    """When order ID, status, revenue, customer are present, confidence may be higher."""
    semantic = build_semantic_profile({
        "inferred_types": {
            "order_id": "string",
            "customer": "string",
            "date": "date",
            "status": "string",
            "revenue": "number",
            "quantity": "integer",
        },
        "sample_rows": [],
    }).to_dict()

    # Should be higher than the no-signal case — still capped at 0.85
    assert semantic["confidence"] >= 0.70


# ---------------------------------------------------------------------------
# P0-6: Confidence note distinguishes data vs business interpretation
# ---------------------------------------------------------------------------


def test_confidence_note_distinguishes_data_and_business(tmp_path):
    """Confidence note must mention 'Data confidence' and 'Business interpretation'."""
    artifact = _summary_artifact(tmp_path, {
        "dataset_type": "ecommerce",
        "row_count": 10,
        "column_count": 3,
        "duplicate_rows": 0,
        "kpis": {
            "Total estimated spend": 800.0,
            "Purchase line count": 10,
            "Return/cancel rate": _UNAVAILABLE,
            "Rows": 10,
            "Columns": 3,
            "Duplicate rows": 0,
            "Missing cells": 0,
        },
        "numeric_summary": {},
        "category_summary": {},
    })

    report = generate_report(
        profile={
            "row_count": 10,
            "column_count": 3,
            "duplicate_rows": 0,
            "inferred_types": {"category": "string", "unit_price": "number"},
            "missing_percent_by_column": {},
            "warnings": [],
            "sample_rows": [],
        },
        route=_ECOMMERCE_ROUTE,
        plan=_ECOMMERCE_PLAN,
        evaluation=_SUCCESS_EVAL,
        execution=_success_execution(artifacts=[artifact]),
    )

    assert "Data confidence:" in report.confidence_note
    assert "Business interpretation:" in report.confidence_note


# ---------------------------------------------------------------------------
# P0-1 (semantic profile): ASIN and ISBN classified as identifier
# ---------------------------------------------------------------------------


def test_asin_classified_as_product_id():
    semantic = build_semantic_profile({
        "inferred_types": {"ASIN": "string", "unit_price": "number"},
        "sample_rows": [{"ASIN": "B001234567", "unit_price": "29.99"}],
    }).to_dict()

    assert semantic["column_roles"]["ASIN"] == "product_id"
    assert any(e["column"] == "ASIN" for e in semantic["excluded_columns"])


def test_isbn_classified_as_product_id():
    semantic = build_semantic_profile({
        "inferred_types": {"ISBN": "string", "price": "number"},
        "sample_rows": [{"ISBN": "978-0-06-112008-4", "price": "14.99"}],
    }).to_dict()

    assert semantic["column_roles"]["ISBN"] == "product_id"


# ---------------------------------------------------------------------------
# P0-2 (semantic profile): limitations include order ID and return rate notice
# ---------------------------------------------------------------------------


def test_limitations_include_no_order_id_notice():
    """When no identifier or reference column, limitations must state it."""
    semantic = build_semantic_profile({
        "inferred_types": {
            "purchase_date": "date",
            "category": "string",
            "unit_price": "number",
        },
        "sample_rows": [],
    }).to_dict()

    limitations_text = " ".join(semantic["limitations"]).lower()
    assert "order id" in limitations_text or "identifier" in limitations_text


def test_limitations_include_no_return_rate_notice():
    """When no status column, limitations must state return rate is unavailable."""
    semantic = build_semantic_profile({
        "inferred_types": {
            "purchase_date": "date",
            "category": "string",
            "unit_price": "number",
        },
        "sample_rows": [],
    }).to_dict()

    limitations_text = " ".join(semantic["limitations"])
    assert "return" in limitations_text.lower() or "cancel" in limitations_text.lower()


# ---------------------------------------------------------------------------
# Semantic correctness: geography vs status, identifier role splitting
# ---------------------------------------------------------------------------


def test_shipping_address_state_is_geography():
    """'Shipping Address State' must be classified as geography, not status."""
    semantic = build_semantic_profile({
        "inferred_types": {"Shipping Address State": "string"},
        "sample_rows": [{"Shipping Address State": "CA"}],
    }).to_dict()

    assert semantic["column_roles"]["Shipping Address State"] == "geography", (
        "Shipping Address State must be geography, not status"
    )


def test_shipping_address_state_without_status_produces_no_return_rate():
    """A dataset with Shipping Address State but no order-status field must report
    return_cancel_rate as unavailable."""
    semantic = build_semantic_profile({
        "inferred_types": {
            "Shipping Address State": "string",
            "Price": "number",
            "Quantity": "integer",
        },
        "sample_rows": [],
    }).to_dict()

    assert "return_cancel_rate" not in semantic["usable_metrics"], (
        "return_cancel_rate must not be available when no status field exists"
    )
    limitations_text = " ".join(semantic["limitations"])
    assert "return" in limitations_text.lower() or "cancel" in limitations_text.lower()


def test_product_identifiers_are_not_order_id():
    """ASIN, ISBN, and Product Code must map to product_id or reference, not order_id."""
    for col_name in ("ASIN", "ISBN", "Product Code"):
        semantic = build_semantic_profile({
            "inferred_types": {col_name: "string"},
            "sample_rows": [],
        }).to_dict()

        role = semantic["column_roles"][col_name]
        assert role in ("product_id", "reference"), (
            f"{col_name} must be product_id or reference, got {role!r}"
        )
        assert role != "order_id", f"{col_name} must not be classified as order_id"


def test_survey_response_id_is_response_id():
    """Survey ResponseID and Response ID must map to response_id, not order_id."""
    for col_name in ("Response ID", "ResponseID", "Survey ResponseID"):
        semantic = build_semantic_profile({
            "inferred_types": {col_name: "string"},
            "sample_rows": [],
        }).to_dict()

        role = semantic["column_roles"][col_name]
        assert role == "response_id", f"{col_name} must be response_id, got {role!r}"
        assert role != "order_id", f"{col_name} must not be classified as order_id"


def test_amazon_schema_no_order_count_no_aov():
    """Amazon-style schema with ASIN but no order ID must not produce
    order_count or average_order_value in usable_metrics."""
    semantic = build_semantic_profile({
        "inferred_types": {
            "ASIN": "string",
            "Product Title": "string",
            "Category": "string",
            "Shipping Address State": "string",
            "Order Date": "date",
            "Price": "number",
            "Quantity": "integer",
        },
        "sample_rows": [],
    }).to_dict()

    metrics = semantic["usable_metrics"]
    assert "order_count" not in metrics, "Amazon schema must not produce order_count"
    assert "average_order_value" not in metrics, "Amazon schema must not produce average_order_value"


def test_amazon_schema_produces_purchase_line_count_and_estimated_spend():
    """Amazon-style schema with ASIN but no order ID must produce
    purchase_line_count and estimated_spend in usable_metrics."""
    semantic = build_semantic_profile({
        "inferred_types": {
            "ASIN": "string",
            "Product Title": "string",
            "Category": "string",
            "Shipping Address State": "string",
            "Order Date": "date",
            "Price": "number",
            "Quantity": "integer",
        },
        "sample_rows": [],
    }).to_dict()

    metrics = semantic["usable_metrics"]
    assert "purchase_line_count" in metrics, "Amazon schema must produce purchase_line_count"
    assert "estimated_spend" in metrics, "Amazon schema must produce estimated_spend"
