"""Tests for backend.services.report_generator."""
from services.evaluator import ExecutionEvaluation
from services.report_generator import ReportPayload, generate_report
from services.sandbox_runner import ArtifactMetadata, SandboxResult


def _artifact(name: str, content_type: str = "application/json") -> ArtifactMetadata:
    return ArtifactMetadata(
        name=name,
        path=f"/tmp/run/{name}",
        size_bytes=100,
        content_type=content_type,
        url=f"/api/runs/run/{name}",
    )


def _success_execution(artifacts=None) -> SandboxResult:
    return SandboxResult(
        run_id="run1",
        status="success",
        exit_code=0,
        stdout="Processed 3 rows",
        stderr="",
        timed_out=False,
        duration_ms=200,
        artifacts=artifacts or [],
        error=None,
    )


def _failed_execution() -> SandboxResult:
    return SandboxResult(
        run_id="run1",
        status="failed",
        exit_code=1,
        stdout="",
        stderr="ValueError: bad data",
        timed_out=False,
        duration_ms=50,
        artifacts=[],
        error="Generated analysis exited with an error.",
    )


_PROFILE = {
    "row_count": 3,
    "column_count": 3,
    "duplicate_rows": 0,
    "inferred_types": {"order_date": "date", "customer": "string", "revenue": "number"},
    "missing_percent_by_column": {"order_date": 0.0, "customer": 0.0, "revenue": 0.0},
    "warnings": [],
    "sample_rows": [],
}

_ROUTE = {"dataset_type": "sales", "confidence": 0.9, "explanation": "test"}

_PLAN = {
    "likely_kpis": ["Total revenue", "Average revenue"],
    "business_questions": ["How is performance trending?"],
    "recommended_transformations": [],
    "recommended_charts": [],
    "anomaly_checks": [],
}

_ECOMMERCE_PROFILE = {
    "row_count": 3,
    "column_count": 7,
    "duplicate_rows": 0,
    "inferred_types": {
        "order_id": "string",
        "category": "string",
        "channel": "string",
        "device": "string",
        "status": "string",
        "net_revenue": "number",
        "quantity": "integer",
    },
    "missing_percent_by_column": {},
    "warnings": [],
    "sample_rows": [],
}

_SUCCESS_EVALUATION = ExecutionEvaluation(
    outcome="success", note="Completed in 200 ms with 1 artifact."
)
_FAILED_EVALUATION = ExecutionEvaluation(
    outcome="recoverable", note="Exit code 1. Stderr hint: ValueError: bad data"
)


def test_generate_report_success_has_executive_summary():
    report = generate_report(
        profile=_PROFILE,
        route=_ROUTE,
        plan=_PLAN,
        evaluation=_SUCCESS_EVALUATION,
        execution=_success_execution(),
    )
    assert isinstance(report, ReportPayload)
    assert report.is_partial is False
    assert len(report.executive_summary) > 0
    assert "3" in report.executive_summary  # row count grounded


def test_generate_report_success_has_anomaly_table():
    report = generate_report(
        profile=_PROFILE,
        route=_ROUTE,
        plan=_PLAN,
        evaluation=_SUCCESS_EVALUATION,
        execution=_success_execution(),
    )
    assert any(row.check == "Duplicate rows" for row in report.anomaly_table)
    assert any(row.check == "Missing cells" for row in report.anomaly_table)


def test_generate_report_success_has_recommendations():
    report = generate_report(
        profile={**_PROFILE, "warnings": ["High missingness in revenue column"]},
        route=_ROUTE,
        plan=_PLAN,
        evaluation=_SUCCESS_EVALUATION,
        execution=_success_execution(),
    )
    assert len(report.business_recommendations) > 0
    assert any("missing" in r.lower() or "duplicate" in r.lower() or "investigate" in r.lower()
               for r in report.business_recommendations)


def test_generate_report_failed_is_partial():
    report = generate_report(
        profile=_PROFILE,
        route=_ROUTE,
        plan=_PLAN,
        evaluation=_FAILED_EVALUATION,
        execution=_failed_execution(),
    )
    assert report.is_partial is True
    assert len(report.kpi_cards) == 0
    assert "could not be completed" in report.executive_summary.lower()


def test_generate_report_chart_artifacts_extracted():
    artifacts = [
        _artifact("summary.json", "application/json"),
        _artifact("missing_values.svg", "image/svg+xml"),
        _artifact("histogram_revenue.svg", "image/svg+xml"),
    ]
    report = generate_report(
        profile=_PROFILE,
        route=_ROUTE,
        plan=_PLAN,
        evaluation=_SUCCESS_EVALUATION,
        execution=_success_execution(artifacts=artifacts),
    )
    assert len(report.chart_artifacts) == 2


def test_generate_report_to_dict_complete():
    report = generate_report(
        profile=_PROFILE,
        route=_ROUTE,
        plan=_PLAN,
        evaluation=_SUCCESS_EVALUATION,
        execution=_success_execution(),
    )
    d = report.to_dict()
    required_keys = {
        "executive_summary", "kpi_cards", "top_findings", "anomaly_table",
        "data_quality_warnings", "business_recommendations", "confidence_note",
        "is_partial", "evaluator_note", "chart_artifacts", "revised", "revision_note",
    }
    assert required_keys.issubset(d.keys())


def test_generate_report_prioritizes_ecommerce_business_kpis(tmp_path):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        """{
          "dataset_type": "ecommerce",
          "row_count": 3,
          "column_count": 7,
          "duplicate_rows": 0,
          "kpis": {
            "Rows": 3,
            "Columns": 7,
            "Net revenue": 300,
            "Order count": 2,
            "Average order value": 150,
            "Return/cancel rate": 33.33,
            "Discount rate": 5
          },
          "numeric_summary": {"net_revenue": {"count": 3, "sum": 300, "mean": 100, "min": 50, "max": 150}},
          "category_summary": {"category": [["Shoes", 2]], "channel": [["Paid", 2]]}
        }""",
        encoding="utf-8",
    )
    artifact = ArtifactMetadata(
        name="summary.json",
        path=str(summary_path),
        size_bytes=summary_path.stat().st_size,
        content_type="application/json",
        url="/api/runs/run/summary.json",
    )

    report = generate_report(
        profile=_ECOMMERCE_PROFILE,
        route={"dataset_type": "ecommerce", "confidence": 0.95, "explanation": "test"},
        plan={"likely_kpis": ["Net revenue"], "business_questions": [], "recommended_transformations": [], "recommended_charts": [], "anomaly_checks": []},
        evaluation=_SUCCESS_EVALUATION,
        execution=_success_execution(artifacts=[artifact]),
    )

    assert [card.label for card in report.kpi_cards[:3]] == [
        "Net revenue",
        "Order count",
        "Average order value",
    ]
    assert any("Return/cancel rate" in finding.description for finding in report.top_findings)
    assert any("discount" in rec.lower() for rec in report.business_recommendations)
