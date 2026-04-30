"""run_store — lightweight SQLite persistence for run metadata.

Tracks each pipeline run from upload through report generation.  Provides
enough state for:
- progress polling (GET /api/runs/{run_id})
- export endpoints (report.md, findings.json, analysis.py)
- TTL-based expiry marking

The DB file is created on first use in the OS temp directory alongside the
run artifact directories.  It is not a source of truth for artifacts (the
filesystem is), but it makes run state observable without reading artifact
files on every request.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


_DB_PATH = Path(tempfile.gettempdir()) / "databrief-ai-runs" / "runs.db"


class RunStatus(str, Enum):
    UPLOADED = "uploaded"
    PROFILED = "profiled"
    PLANNED = "planned"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    REPAIRING = "repairing"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class RunRecord:
    run_id: str
    created_at: str
    status: RunStatus
    filename: str
    profile_json: dict
    route_json: dict
    plan_json: dict
    expires_at: str
    retry_count: int = 0
    evaluation_result: dict = field(default_factory=dict)
    report_json: dict = field(default_factory=dict)
    generated_code: str = ""
    summary_errors: list[str] = field(default_factory=list)

    def to_status_dict(self) -> dict[str, Any]:
        """Compact dict for the status endpoint — no large payloads."""
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "filename": self.filename,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "retry_count": self.retry_count,
            "evaluation": self.evaluation_result,
            "summary_errors": self.summary_errors,
            "route": self.route_json,
        }

    def render_report_markdown(self) -> str | None:
        """Render the stored report as a Markdown document."""
        rpt = self.report_json
        if not rpt:
            return None

        lines: list[str] = []
        lines.append(f"# DataBrief AI — Analysis Report")
        lines.append(f"\n**File:** {self.filename}  ")
        lines.append(f"**Run ID:** {self.run_id}  ")
        lines.append(f"**Generated:** {self.created_at}  ")
        if rpt.get("is_partial"):
            lines.append(f"\n> ⚠ Partial result — execution did not complete successfully.")

        summary = rpt.get("executive_summary", "")
        if summary:
            lines.append(f"\n## Executive Summary\n\n{summary}")

        kpis = rpt.get("kpi_cards", [])
        if kpis:
            lines.append("\n## Key Metrics\n")
            lines.append("| Metric | Value | Source |")
            lines.append("|--------|-------|--------|")
            for card in kpis:
                lines.append(f"| {card['label']} | {card['value']} | {card['source']} |")

        findings = rpt.get("top_findings", [])
        if findings:
            lines.append("\n## Top Findings\n")
            for f in findings:
                lines.append(f"- {f['description']}")

        anomalies = rpt.get("anomaly_table", [])
        if anomalies:
            lines.append("\n## Anomaly Checks\n")
            lines.append("| Check | Value | Status |")
            lines.append("|-------|-------|--------|")
            for row in anomalies:
                lines.append(f"| {row['check']} | {row['value']} | {row['flag']} |")

        warnings = rpt.get("data_quality_warnings", [])
        if warnings:
            lines.append("\n## Data Quality Warnings\n")
            for w in warnings:
                lines.append(f"- {w}")

        recs = rpt.get("business_recommendations", [])
        if recs:
            lines.append("\n## Recommendations\n")
            for r in recs:
                lines.append(f"- {r}")

        limitations = rpt.get("dataset_limitations", [])
        if limitations:
            lines.append("\n## Dataset Limitations\n")
            for item in limitations:
                lines.append(f"- {item}")

        note = rpt.get("confidence_note", "")
        if note:
            lines.append(f"\n---\n\n*{note}*")

        if rpt.get("revised"):
            lines.append(f"\n*Groundedness revision: {rpt.get('revision_note', '')}*")

        return "\n".join(lines)

    def get_findings(self) -> dict[str, Any] | None:
        """Return a structured findings export dict."""
        rpt = self.report_json
        if not rpt:
            return None
        return {
            "run_id": self.run_id,
            "filename": self.filename,
            "created_at": self.created_at,
            "status": self.status.value,
            "executive_summary": rpt.get("executive_summary", ""),
            "kpi_cards": rpt.get("kpi_cards", []),
            "top_findings": rpt.get("top_findings", []),
            "anomaly_table": rpt.get("anomaly_table", []),
            "data_quality_warnings": rpt.get("data_quality_warnings", []),
            "business_recommendations": rpt.get("business_recommendations", []),
            "dataset_limitations": rpt.get("dataset_limitations", []),
            "confidence_note": rpt.get("confidence_note", ""),
            "is_partial": rpt.get("is_partial", False),
            "groundedness": {
                "revised": rpt.get("revised", False),
                "revision_note": rpt.get("revision_note", ""),
            },
        }


class RunStore:
    """SQLite-backed store for run metadata."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db_path = db_path
        self.init_db()

    def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id        TEXT PRIMARY KEY,
                    created_at    TEXT NOT NULL,
                    status        TEXT NOT NULL,
                    filename      TEXT NOT NULL,
                    profile_json  TEXT NOT NULL DEFAULT '{}',
                    route_json    TEXT NOT NULL DEFAULT '{}',
                    plan_json     TEXT NOT NULL DEFAULT '{}',
                    retry_count   INTEGER NOT NULL DEFAULT 0,
                    evaluation_json TEXT NOT NULL DEFAULT '{}',
                    report_json   TEXT NOT NULL DEFAULT '{}',
                    generated_code TEXT NOT NULL DEFAULT '',
                    summary_errors TEXT NOT NULL DEFAULT '[]',
                    expires_at    TEXT NOT NULL
                )
            """)

    def create(
        self,
        *,
        run_id: str,
        filename: str,
        profile_json: dict,
        route_json: dict,
        plan_json: dict,
        ttl_hours: int,
    ) -> None:
        now = _utcnow()
        expires = _utcnow_plus(ttl_hours)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs
                    (run_id, created_at, status, filename,
                     profile_json, route_json, plan_json, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    now,
                    RunStatus.UPLOADED.value,
                    filename,
                    json.dumps(profile_json),
                    json.dumps(route_json),
                    json.dumps(plan_json),
                    expires,
                ),
            )

    def set_status(self, run_id: str, status: RunStatus) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ? WHERE run_id = ?",
                (status.value, run_id),
            )

    def set_generated_code(self, run_id: str, code: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET generated_code = ? WHERE run_id = ?",
                (code, run_id),
            )

    def finish(
        self,
        *,
        run_id: str,
        status: RunStatus,
        retry_count: int,
        evaluation_result: dict,
        report_json: dict,
        summary_errors: list[str],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs SET
                    status = ?,
                    retry_count = ?,
                    evaluation_json = ?,
                    report_json = ?,
                    summary_errors = ?
                WHERE run_id = ?
                """,
                (
                    status.value,
                    retry_count,
                    json.dumps(evaluation_result),
                    json.dumps(report_json),
                    json.dumps(summary_errors),
                    run_id,
                ),
            )

    def get(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def mark_expired(self) -> int:
        """Mark runs whose expires_at has passed as EXPIRED. Returns count."""
        now = _utcnow()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE runs SET status = ? WHERE expires_at < ? AND status != ?",
                (RunStatus.EXPIRED.value, now, RunStatus.EXPIRED.value),
            )
            return cur.rowcount

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utcnow_plus(hours: int) -> str:
    return datetime.fromtimestamp(
        time.time() + hours * 3600, tz=timezone.utc
    ).isoformat()


def _row_to_record(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        created_at=row["created_at"],
        status=RunStatus(row["status"]),
        filename=row["filename"],
        profile_json=json.loads(row["profile_json"]),
        route_json=json.loads(row["route_json"]),
        plan_json=json.loads(row["plan_json"]),
        retry_count=row["retry_count"],
        evaluation_result=json.loads(row["evaluation_json"]),
        report_json=json.loads(row["report_json"]),
        generated_code=row["generated_code"],
        summary_errors=json.loads(row["summary_errors"]),
        expires_at=row["expires_at"],
    )
