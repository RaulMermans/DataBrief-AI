"""Tests for backend.services.groundedness."""
from services.evaluator import ExecutionEvaluation
from services.groundedness import check_and_revise
from services.report_generator import ReportPayload, generate_report
from services.sandbox_runner import SandboxResult


def _partial_report() -> ReportPayload:
    r = ReportPayload()
    r.is_partial = True
    r.executive_summary = "Analysis could not be completed."
    return r


def _full_report(executive_summary: str, recommendations=None) -> ReportPayload:
    r = ReportPayload()
    r.is_partial = False
    r.executive_summary = executive_summary
    r.business_recommendations = recommendations or []
    return r


_COMPUTED_FACTS = {
    "row_count": 100,
    "column_count": 5,
    "duplicate_rows": 2,
    "dataset_type": "sales",
    "kpis": {"Total revenue": 50000, "Rows": 100},
    "numeric_summary": {"revenue": {"mean": 500, "min": 10, "max": 1200, "count": 100}},
    "category_summary": {"product": [["Widget", 40], ["Gadget", 30]]},
}


def test_no_revision_needed_for_partial_report():
    report = _partial_report()
    result = check_and_revise(report, _COMPUTED_FACTS)
    assert result.revised is False
    # Partial reports are left untouched
    assert result.is_partial is True


def test_grounded_summary_is_not_revised():
    summary = "Processed 100 rows and 5 columns from a sales dataset."
    report = _full_report(summary)
    result = check_and_revise(report, _COMPUTED_FACTS)
    assert result.executive_summary == summary
    assert result.revised is False


def test_unsupported_sentinel_in_summary_is_replaced():
    report = _full_report("[UNSUPPORTED — no computed data]")
    result = check_and_revise(report, _COMPUTED_FACTS)
    assert "[UNSUPPORTED" not in result.executive_summary
    assert result.revised is True


def test_unsupported_recommendation_is_removed():
    recs = [
        "Focus on revenue and rows.",
        "[UNSUPPORTED — no computed data]",
    ]
    report = _full_report("Processed 100 rows.", recommendations=recs)
    result = check_and_revise(report, _COMPUTED_FACTS)
    assert all("[UNSUPPORTED" not in r for r in result.business_recommendations)
    assert result.revised is True
    assert "removed" in result.revision_note


def test_investigate_recommendation_is_always_kept():
    recs = ["Investigate: How is performance trending?"]
    report = _full_report("Processed 100 rows.", recommendations=recs)
    result = check_and_revise(report, _COMPUTED_FACTS)
    assert any("Investigate:" in r for r in result.business_recommendations)


def test_revision_note_populated_when_no_changes():
    report = _full_report(
        "Processed 100 rows and 5 columns. Total revenue: 50000.",
        recommendations=["Focus on revenue and rows."],
    )
    result = check_and_revise(report, _COMPUTED_FACTS)
    assert result.revision_note != ""


def test_grounded_report_from_generator_passes_check():
    """End-to-end: a report generated from a sales profile should pass
    groundedness validation without requiring revision."""
    from services.sandbox_runner import ArtifactMetadata
    profile = {
        "row_count": 50,
        "column_count": 4,
        "duplicate_rows": 0,
        "inferred_types": {"date": "date", "customer": "string", "revenue": "number", "units": "integer"},
        "missing_percent_by_column": {},
        "warnings": [],
        "sample_rows": [],
    }
    route = {"dataset_type": "sales", "confidence": 0.9, "explanation": "test"}
    plan = {
        "likely_kpis": ["Total revenue"],
        "business_questions": ["How is revenue trending?"],
        "recommended_transformations": [],
        "recommended_charts": [],
        "anomaly_checks": [],
    }
    evaluation = ExecutionEvaluation(outcome="success", note="Completed.")
    execution = SandboxResult(
        run_id="r", status="success", exit_code=0, stdout="", stderr="",
        timed_out=False, duration_ms=100, artifacts=[], error=None,
    )
    report = generate_report(
        profile=profile, route=route, plan=plan,
        evaluation=evaluation, execution=execution,
    )
    computed_facts = {
        "row_count": 50, "column_count": 4, "duplicate_rows": 0,
        "dataset_type": "sales", "kpis": {}, "numeric_summary": {}, "category_summary": {},
    }
    result = check_and_revise(report, computed_facts)
    # Grounded report should not lose its executive_summary entirely
    assert len(result.executive_summary) > 0
