"""Tests for backend.services.summary_validator."""
import pytest
from backend.services.summary_validator import is_summary_valid, validate_summary_json

_VALID_SUMMARY = {
    "dataset_type": "sales",
    "row_count": 100,
    "column_count": 5,
    "kpis": {"Rows": 100, "Total revenue": 9500.0},
    "numeric_summary": {"revenue": {"count": 100, "mean": 95.0}},
    "category_summary": {"product": [["Widget", 40]]},
}


def test_valid_summary_returns_no_errors():
    assert validate_summary_json(_VALID_SUMMARY) == []


def test_valid_summary_is_valid():
    assert is_summary_valid(_VALID_SUMMARY) is True


def test_missing_required_field():
    bad = {k: v for k, v in _VALID_SUMMARY.items() if k != "kpis"}
    errors = validate_summary_json(bad)
    assert any("kpis" in e for e in errors)


def test_all_required_fields_present():
    required = {"dataset_type", "row_count", "column_count", "kpis", "numeric_summary", "category_summary"}
    for field in required:
        bad = {k: v for k, v in _VALID_SUMMARY.items() if k != field}
        errors = validate_summary_json(bad)
        assert errors, f"Expected errors for missing '{field}'"
        assert any(field in e for e in errors), f"Error should mention field '{field}'"


def test_non_dict_summary():
    errors = validate_summary_json(["not", "a", "dict"])
    assert errors
    assert any("object" in e or "dict" in e for e in errors)


def test_kpis_must_be_dict():
    bad = {**_VALID_SUMMARY, "kpis": ["not", "a", "dict"]}
    errors = validate_summary_json(bad)
    assert any("kpis" in e for e in errors)


def test_row_count_must_be_numeric():
    bad = {**_VALID_SUMMARY, "row_count": "one-hundred"}
    errors = validate_summary_json(bad)
    assert any("row_count" in e for e in errors)


def test_numeric_summary_must_be_dict():
    bad = {**_VALID_SUMMARY, "numeric_summary": "not-a-dict"}
    errors = validate_summary_json(bad)
    assert any("numeric_summary" in e for e in errors)


def test_empty_dict_is_invalid():
    errors = validate_summary_json({})
    assert len(errors) >= 6  # all required fields missing


def test_none_is_invalid():
    errors = validate_summary_json(None)
    assert errors
