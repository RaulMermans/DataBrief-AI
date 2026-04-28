"""Tests for claim/evidence-based groundedness model."""
import pytest
from services.evaluator import ExecutionEvaluation
from services.groundedness import (
    GroundedClaim,
    _build_evidence_index,
    check_and_revise,
)
from services.report_generator import ReportPayload, generate_report
from services.sandbox_runner import SandboxResult

_COMPUTED_FACTS = {
    "row_count": 100,
    "column_count": 5,
    "duplicate_rows": 2,
    "dataset_type": "sales",
    "kpis": {"Total revenue": 50000, "Rows": 100},
    "numeric_summary": {"revenue": {"mean": 500, "min": 10, "max": 1200, "count": 100}},
    "category_summary": {"product": [["Widget", 40], ["Gadget", 30]]},
}


def _full_report(executive_summary: str = "", recommendations=None) -> ReportPayload:
    r = ReportPayload()
    r.is_partial = False
    r.executive_summary = executive_summary
    r.business_recommendations = recommendations or []
    return r


# ---------------------------------------------------------------------------
# Evidence index
# ---------------------------------------------------------------------------


def test_evidence_index_includes_kpi_labels():
    idx = _build_evidence_index(_COMPUTED_FACTS)
    assert "total revenue" in idx
    assert idx["total revenue"].startswith("summary.json:kpis")


def test_evidence_index_includes_column_names():
    idx = _build_evidence_index(_COMPUTED_FACTS)
    assert "revenue" in idx


def test_evidence_index_includes_dataset_type():
    idx = _build_evidence_index(_COMPUTED_FACTS)
    assert "sales" in idx


def test_evidence_index_includes_generic_structural_tokens():
    idx = _build_evidence_index(_COMPUTED_FACTS)
    assert "rows" in idx
    assert "columns" in idx
    assert "duplicate" in idx


# ---------------------------------------------------------------------------
# check_and_revise — claim population
# ---------------------------------------------------------------------------


def test_partial_report_not_revised():
    r = ReportPayload()
    r.is_partial = True
    r.executive_summary = "Could not complete."
    result = check_and_revise(r, _COMPUTED_FACTS)
    assert result.revised is False
    assert result.claims == []


def test_report_claims_are_populated():
    r = _full_report(
        "Processed 100 rows and 5 columns from a sales dataset.",
        recommendations=["Focus on revenue and rows."],
    )
    result = check_and_revise(r, _COMPUTED_FACTS)
    assert len(result.claims) > 0


def test_supported_claims_have_source():
    r = _full_report("Processed 100 rows and 5 columns.")
    result = check_and_revise(r, _COMPUTED_FACTS)
    for claim in result.claims:
        if claim["status"] == "supported":
            assert claim["source"] != "none"


def test_unsupported_sentinel_claim_marked_unsupported():
    r = _full_report("[UNSUPPORTED — no computed data]")
    result = check_and_revise(r, _COMPUTED_FACTS)
    unsupported = [c for c in result.claims if c["status"] == "unsupported"]
    assert len(unsupported) > 0


def test_investigate_recommendation_marked_uncertain():
    r = _full_report(
        "Processed 100 rows.",
        recommendations=["Investigate: How is revenue trending?"],
    )
    result = check_and_revise(r, _COMPUTED_FACTS)
    investigate_claims = [
        c for c in result.claims
        if "Investigate:" in c["claim"] and c["claim_type"] == "recommendation"
    ]
    assert len(investigate_claims) == 1
    assert investigate_claims[0]["status"] == "uncertain"


def test_unsupported_recommendation_removed():
    recs = [
        "Focus on revenue and rows.",
        "[UNSUPPORTED — no computed data]",
    ]
    r = _full_report("Processed 100 rows.", recommendations=recs)
    result = check_and_revise(r, _COMPUTED_FACTS)
    assert all("[UNSUPPORTED" not in rec for rec in result.business_recommendations)
    assert result.revised is True


def test_grounded_summary_not_revised():
    summary = "Processed 100 rows and 5 columns from a sales dataset."
    r = _full_report(summary)
    result = check_and_revise(r, _COMPUTED_FACTS)
    assert result.executive_summary == summary
    assert result.revised is False


def test_claims_list_serialisable():
    r = _full_report(
        "Processed 100 rows and 5 columns.",
        recommendations=["Focus on revenue.", "Investigate: trends?"],
    )
    result = check_and_revise(r, _COMPUTED_FACTS)
    for claim in result.claims:
        assert "claim" in claim
        assert "claim_type" in claim
        assert "source" in claim
        assert "status" in claim
        assert claim["status"] in {"supported", "unsupported", "uncertain"}


def test_kpi_card_claims_present():
    from services.report_generator import KpiCard
    r = _full_report("Processed 100 rows.")
    r.kpi_cards = [
        KpiCard(label="Total revenue", value=50000, source="summary.json:kpis"),
        KpiCard(label="Unknown KPI", value=999, source="summary.json:kpis"),
    ]
    result = check_and_revise(r, _COMPUTED_FACTS)
    kpi_claims = [c for c in result.claims if c["claim_type"] == "kpi"]
    assert len(kpi_claims) == 2
    supported = [c for c in kpi_claims if c["status"] == "supported"]
    assert len(supported) >= 1  # "Total revenue" should be supported
