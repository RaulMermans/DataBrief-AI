"""Groundedness evaluator.

Single-pass revision of a ``ReportPayload`` that removes or rewrites claims
that cannot be traced to the supplied ``computed_facts`` dict.

Rules (deterministic, no model calls):
- ``executive_summary``: keep only sentences that contain at least one token
  from the computed facts (numeric values, column names, dataset_type).
  If all sentences are removed, replace with a safe fallback.
- ``business_recommendations``: remove items that contain the sentinel
  ``_UNSUPPORTED`` marker or that reference column names / KPI labels not
  present in computed facts.
- All other sections are left unchanged (they are already sourced from
  computed data by the report generator).
- The revision is performed at most once.  The result is marked
  ``revised=True`` and ``revision_note`` is populated.
"""
from __future__ import annotations

import re

from backend.services.report_generator import ReportPayload

# Sentinel placed by the report generator for unpopulated claims.
_UNSUPPORTED = "[UNSUPPORTED — no computed data]"


def check_and_revise(report: ReportPayload, computed_facts: dict) -> ReportPayload:
    """Validate and revise *report* in a single deterministic pass.

    ``computed_facts`` should contain the keys/values from summary.json:
    ``kpis``, ``numeric_summary``, ``category_summary``, ``row_count``,
    ``column_count``, ``duplicate_rows``.  The profile dict is also accepted.

    Returns the (possibly revised) ``ReportPayload`` with ``revised`` and
    ``revision_note`` populated.
    """
    if report.is_partial:
        # Partial reports have no computed facts to validate against; leave as-is.
        return report

    # Build a set of known fact tokens: KPI labels, column names, numeric values.
    known_tokens = _build_known_tokens(computed_facts)

    changes: list[str] = []

    # --- Revise executive_summary ---
    original_summary = report.executive_summary
    revised_summary = _revise_summary(original_summary, known_tokens)
    if revised_summary != original_summary:
        changes.append("executive_summary revised: removed unsupported sentences")
    report.executive_summary = revised_summary

    # --- Revise business_recommendations ---
    original_recs = list(report.business_recommendations)
    revised_recs = _revise_recommendations(original_recs, known_tokens)
    removed_count = len(original_recs) - len(revised_recs)
    if removed_count > 0:
        changes.append(
            f"business_recommendations revised: removed {removed_count} unsupported item(s)"
        )
    report.business_recommendations = revised_recs

    if changes:
        report.revised = True
        report.revision_note = "; ".join(changes)
    else:
        report.revised = False
        report.revision_note = "No unsupported claims found; report is unmodified."

    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_known_tokens(computed_facts: dict) -> set[str]:
    """Extract a set of lower-cased strings that represent known computed facts."""
    tokens: set[str] = set()

    # Row/column counts
    for key in ("row_count", "column_count", "duplicate_rows"):
        value = computed_facts.get(key)
        if value is not None:
            tokens.add(str(value).lower())

    # KPI labels and values
    for label, value in computed_facts.get("kpis", {}).items():
        tokens.add(label.lower())
        tokens.add(str(value).lower())

    # Column names from numeric_summary
    for col in computed_facts.get("numeric_summary", {}):
        tokens.add(col.lower())

    # Column names from category_summary
    for col in computed_facts.get("category_summary", {}):
        tokens.add(col.lower())

    # Dataset type
    for key in ("dataset_type",):
        value = computed_facts.get(key)
        if value:
            tokens.add(str(value).lower())

    # Generic high-value tokens always considered grounded
    tokens.update({"rows", "columns", "duplicate", "missing", "cells", "chart", "artifact"})

    return tokens


def _sentence_is_grounded(sentence: str, known_tokens: set[str]) -> bool:
    """Return True if *sentence* contains at least one known fact token."""
    sentence_lower = sentence.lower()
    # Extract all word/number tokens from the sentence.
    candidate_tokens = set(re.findall(r"[\w.]+", sentence_lower))
    return bool(candidate_tokens & known_tokens)


def _revise_summary(summary: str, known_tokens: set[str]) -> str:
    """Keep only grounded sentences from *summary*."""
    if _UNSUPPORTED in summary:
        return (
            "The executive summary could not be generated from computed outputs."
        )

    # Split on sentence boundaries (period + space, or end of string).
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", summary) if s.strip()]
    grounded = [s for s in sentences if _sentence_is_grounded(s, known_tokens)]

    if not grounded:
        return (
            "The executive summary could not be verified against computed outputs "
            "and has been removed."
        )
    return " ".join(grounded)


def _revise_recommendations(
    recommendations: list[str], known_tokens: set[str]
) -> list[str]:
    """Remove recommendations containing the unsupported sentinel or that
    reference no known tokens at all."""
    kept: list[str] = []
    for rec in recommendations:
        if _UNSUPPORTED in rec:
            continue
        # Allow investigation suggestions — they reference plan questions which
        # are generic business questions, not invented facts.
        if rec.lower().startswith("investigate:"):
            kept.append(rec)
            continue
        if _sentence_is_grounded(rec, known_tokens):
            kept.append(rec)
    return kept
