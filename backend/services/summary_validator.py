"""summary_validator — schema validation for summary.json artifacts.

Called after sandbox execution to verify that the generated analysis produced
a well-formed summary.json before the report generator consumes it.

Validation is deterministic (no model calls).  Invalid or incomplete summaries
are flagged; a single repair attempt may be triggered by the repair runner if
the failure is recoverable.
"""
from __future__ import annotations

from typing import Any

REQUIRED_FIELDS: frozenset[str] = frozenset(
    {"dataset_type", "row_count", "column_count", "kpis", "numeric_summary", "category_summary"}
)


def validate_summary_json(summary: Any) -> list[str]:
    """Return a list of validation error strings.

    An empty list means the summary is valid.  The caller should treat a
    non-empty list as a signal that the summary is incomplete or malformed.
    """
    if not isinstance(summary, dict):
        return ["summary.json must be a JSON object, got: " + type(summary).__name__]

    errors: list[str] = []

    for field in sorted(REQUIRED_FIELDS):
        if field not in summary:
            errors.append(f"summary.json is missing required field: '{field}'")

    if "kpis" in summary and not isinstance(summary["kpis"], dict):
        errors.append("summary.json 'kpis' must be a JSON object")

    if "numeric_summary" in summary and not isinstance(summary["numeric_summary"], dict):
        errors.append("summary.json 'numeric_summary' must be a JSON object")

    if "category_summary" in summary and not isinstance(summary["category_summary"], dict):
        errors.append("summary.json 'category_summary' must be a JSON object")

    if "row_count" in summary and not isinstance(summary["row_count"], (int, float)):
        errors.append("summary.json 'row_count' must be numeric")

    if "column_count" in summary and not isinstance(summary["column_count"], (int, float)):
        errors.append("summary.json 'column_count' must be numeric")

    if "dataset_type" in summary and not isinstance(summary["dataset_type"], str):
        errors.append("summary.json 'dataset_type' must be a string")

    return errors


def is_summary_valid(summary: Any) -> bool:
    """Convenience wrapper — True when validate_summary_json returns no errors."""
    return len(validate_summary_json(summary)) == 0
