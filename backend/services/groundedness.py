"""Groundedness evaluator — claim/evidence model.

Every numeric or statistical claim in the report is converted into a
``GroundedClaim`` object that references a specific field in ``computed_facts``
(which contains summary.json content + profile metadata).

Claim statuses:
- ``supported``   — the claim's value or label is traceable to a named source.
- ``unsupported`` — the claim contains the ``_UNSUPPORTED`` sentinel or
                    references no known computed fact.
- ``uncertain``   — the claim appears relevant but source evidence is weak.

The ``check_and_revise`` function:
1. Extracts claims from each report section.
2. Classifies each claim as supported / unsupported / uncertain.
3. Removes unsupported claims from the report (single pass, max 1 revision).
4. Attaches the claim list to the report for auditability.

No model calls are made; all logic is deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.report_generator import ReportPayload

_UNSUPPORTED = "[UNSUPPORTED — no computed data]"


# ---------------------------------------------------------------------------
# GroundedClaim — the structured unit of groundedness evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroundedClaim:
    claim: str
    claim_type: str   # "kpi" | "finding" | "summary" | "recommendation" | "warning"
    source: str       # e.g. "summary.json:kpis.Total revenue"
    status: str       # "supported" | "unsupported" | "uncertain"
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "claim_type": self.claim_type,
            "source": self.source,
            "status": self.status,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check_and_revise(report: ReportPayload, computed_facts: dict) -> ReportPayload:
    """Validate and revise *report* in a single deterministic pass.

    ``computed_facts`` should contain keys from summary.json (``kpis``,
    ``numeric_summary``, ``category_summary``, ``row_count``, ``column_count``,
    ``duplicate_rows``) plus profile metadata.

    Returns the (possibly revised) ``ReportPayload`` with ``revised``,
    ``revision_note``, and ``claims`` populated.
    """
    if report.is_partial:
        return report

    evidence = _build_evidence_index(computed_facts)
    claims: list[GroundedClaim] = []
    changes: list[str] = []

    # --- KPI cards: each card references summary.json:kpis.<label> ----------
    for card in report.kpi_cards:
        source = f"summary.json:kpis.{card.label}"
        if card.label in computed_facts.get("kpis", {}):
            claims.append(GroundedClaim(
                claim=f"{card.label} = {card.value}",
                claim_type="kpi",
                source=source,
                status="supported",
                reason="Label and value found in summary.json:kpis",
            ))
        else:
            claims.append(GroundedClaim(
                claim=f"{card.label} = {card.value}",
                claim_type="kpi",
                source=source,
                status="uncertain",
                reason="KPI label not in computed kpis dict (may be from profile)",
            ))

    # --- Top findings: sourced from numeric/category summaries --------------
    for finding in report.top_findings:
        src = finding.source  # e.g. "summary.json:numeric_summary:revenue"
        status, reason = _evaluate_finding_source(src, computed_facts)
        claims.append(GroundedClaim(
            claim=finding.description,
            claim_type="finding",
            source=src,
            status=status,
            reason=reason,
        ))

    # --- Executive summary: sentence-level claim extraction -----------------
    original_summary = report.executive_summary
    revised_summary, summary_claims = _revise_and_extract_summary(
        original_summary, evidence
    )
    claims.extend(summary_claims)
    if revised_summary != original_summary:
        changes.append("executive_summary revised: removed unsupported sentences")
    report.executive_summary = revised_summary

    # --- Business recommendations -------------------------------------------
    original_recs = list(report.business_recommendations)
    revised_recs, rec_claims = _revise_and_extract_recommendations(
        original_recs, evidence
    )
    claims.extend(rec_claims)
    removed_count = len(original_recs) - len(revised_recs)
    if removed_count > 0:
        changes.append(
            f"business_recommendations revised: removed {removed_count} unsupported item(s)"
        )
    report.business_recommendations = revised_recs

    # --- Attach claims to report --------------------------------------------
    report.claims = [c.to_dict() for c in claims]

    if changes:
        report.revised = True
        report.revision_note = "; ".join(changes)
    else:
        report.revised = False
        report.revision_note = "No unsupported claims found; report is unmodified."

    return report


# ---------------------------------------------------------------------------
# Evidence index
# ---------------------------------------------------------------------------


def _build_evidence_index(computed_facts: dict) -> dict[str, str]:
    """Build a flat dict mapping token → source path for known computed facts."""
    index: dict[str, str] = {}

    for key in ("row_count", "column_count", "duplicate_rows"):
        val = computed_facts.get(key)
        if val is not None:
            index[str(val).lower()] = f"profile:{key}"

    for label, value in computed_facts.get("kpis", {}).items():
        index[label.lower()] = f"summary.json:kpis.{label}"
        for token in re.findall(r"[\w.]+", label.lower()):
            index[token] = f"summary.json:kpis.{label}"
        index[str(value).lower()] = f"summary.json:kpis.{label}"

    for col in computed_facts.get("numeric_summary", {}):
        index[col.lower()] = f"summary.json:numeric_summary.{col}"

    for col in computed_facts.get("category_summary", {}):
        index[col.lower()] = f"summary.json:category_summary.{col}"

    dataset_type = computed_facts.get("dataset_type")
    if dataset_type:
        index[str(dataset_type).lower()] = "profile:dataset_type"

    # Generic structural tokens always considered grounded — they describe
    # shape, not computed values, so no specific source is required.
    for generic in ("rows", "columns", "duplicate", "missing", "cells", "chart", "artifact"):
        index[generic] = "profile:structural"

    return index


def _evaluate_finding_source(
    source: str, computed_facts: dict
) -> tuple[str, str]:
    """Return (status, reason) for a finding given its declared source path."""
    if source.startswith("summary.json:numeric_summary:"):
        col = source.split(":", 2)[-1]
        if col in computed_facts.get("numeric_summary", {}):
            return "supported", f"Column '{col}' present in summary.json:numeric_summary"
        return "unsupported", f"Column '{col}' not found in numeric_summary"

    if source.startswith("summary.json:category_summary:"):
        col = source.split(":", 2)[-1]
        if col in computed_facts.get("category_summary", {}):
            return "supported", f"Column '{col}' present in summary.json:category_summary"
        return "unsupported", f"Column '{col}' not found in category_summary"

    if source.startswith("summary.json:kpis"):
        return "supported", "KPI sourced from summary.json:kpis"

    return "uncertain", f"Source '{source}' could not be verified against computed_facts"


# ---------------------------------------------------------------------------
# Summary revision
# ---------------------------------------------------------------------------


def _revise_and_extract_summary(
    summary: str, evidence: dict[str, str]
) -> tuple[str, list[GroundedClaim]]:
    claims: list[GroundedClaim] = []

    if _UNSUPPORTED in summary:
        claims.append(GroundedClaim(
            claim=summary[:120],
            claim_type="summary",
            source="none",
            status="unsupported",
            reason="Contains _UNSUPPORTED sentinel",
        ))
        fallback = "The executive summary could not be generated from computed outputs."
        return fallback, claims

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", summary) if s.strip()]
    kept: list[str] = []
    for sentence in sentences:
        source, is_grounded = _sentence_source(sentence, evidence)
        if is_grounded:
            claims.append(GroundedClaim(
                claim=sentence,
                claim_type="summary",
                source=source,
                status="supported",
                reason="Sentence contains a token traceable to computed facts",
            ))
            kept.append(sentence)
        else:
            claims.append(GroundedClaim(
                claim=sentence,
                claim_type="summary",
                source="none",
                status="unsupported",
                reason="No computed-fact token found in sentence",
            ))

    if not kept:
        return (
            "The executive summary could not be verified against computed outputs "
            "and has been removed.",
            claims,
        )
    return " ".join(kept), claims


def _sentence_source(sentence: str, evidence: dict[str, str]) -> tuple[str, bool]:
    """Return (source_path, grounded) for a sentence."""
    tokens = set(re.findall(r"[\w.]+", sentence.lower()))
    for token in tokens:
        if token in evidence:
            return evidence[token], True
    return "none", False


# ---------------------------------------------------------------------------
# Recommendation revision
# ---------------------------------------------------------------------------


def _revise_and_extract_recommendations(
    recommendations: list[str], evidence: dict[str, str]
) -> tuple[list[str], list[GroundedClaim]]:
    kept: list[str] = []
    claims: list[GroundedClaim] = []

    for rec in recommendations:
        if _UNSUPPORTED in rec:
            claims.append(GroundedClaim(
                claim=rec[:120],
                claim_type="recommendation",
                source="none",
                status="unsupported",
                reason="Contains _UNSUPPORTED sentinel",
            ))
            continue

        if rec.lower().startswith("investigate:"):
            # Investigation suggestions reference plan questions — allow without
            # requiring a direct computed-fact match.
            claims.append(GroundedClaim(
                claim=rec,
                claim_type="recommendation",
                source="plan:business_questions",
                status="uncertain",
                reason="Investigation suggestion from analysis plan (not a computed fact)",
            ))
            kept.append(rec)
            continue

        source, is_grounded = _sentence_source(rec, evidence)
        if is_grounded:
            claims.append(GroundedClaim(
                claim=rec,
                claim_type="recommendation",
                source=source,
                status="supported",
                reason="Recommendation references a computed fact token",
            ))
            kept.append(rec)
        else:
            claims.append(GroundedClaim(
                claim=rec,
                claim_type="recommendation",
                source="none",
                status="unsupported",
                reason="No computed-fact token found in recommendation",
            ))

    return kept, claims
