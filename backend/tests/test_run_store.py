"""Tests for run_store — SQLite run metadata persistence."""
import tempfile
from pathlib import Path

import pytest

from backend.services.run_store import RunRecord, RunStatus, RunStore


def _store(tmp_path: Path) -> RunStore:
    return RunStore(db_path=tmp_path / "test_runs.db")


def _create(store: RunStore, run_id: str = "run-001", filename: str = "sales.csv") -> None:
    store.create(
        run_id=run_id,
        filename=filename,
        profile_json={"row_count": 10},
        route_json={"dataset_type": "sales"},
        plan_json={"likely_kpis": []},
        ttl_hours=24,
    )


def test_create_and_get(tmp_path: Path):
    store = _store(tmp_path)
    _create(store, run_id="abc123")
    record = store.get("abc123")
    assert record is not None
    assert record.run_id == "abc123"
    assert record.filename == "sales.csv"
    assert record.status == RunStatus.UPLOADED


def test_get_unknown_returns_none(tmp_path: Path):
    store = _store(tmp_path)
    assert store.get("no-such-run") is None


def test_set_status(tmp_path: Path):
    store = _store(tmp_path)
    _create(store)
    store.set_status("run-001", RunStatus.EXECUTING)
    assert store.get("run-001").status == RunStatus.EXECUTING


def test_set_generated_code(tmp_path: Path):
    store = _store(tmp_path)
    _create(store)
    store.set_generated_code("run-001", "print('hello')")
    assert store.get("run-001").generated_code == "print('hello')"


def test_finish_persists_report(tmp_path: Path):
    store = _store(tmp_path)
    _create(store)
    store.finish(
        run_id="run-001",
        status=RunStatus.COMPLETE,
        retry_count=1,
        evaluation_result={"outcome": "success"},
        report_json={"executive_summary": "Processed 10 rows."},
        summary_errors=[],
    )
    record = store.get("run-001")
    assert record.status == RunStatus.COMPLETE
    assert record.retry_count == 1
    assert record.report_json["executive_summary"] == "Processed 10 rows."
    assert record.summary_errors == []


def test_to_status_dict_has_no_absolute_paths(tmp_path: Path):
    store = _store(tmp_path)
    _create(store)
    d = store.get("run-001").to_status_dict()
    assert "run_id" in d
    assert "status" in d
    assert "filename" in d
    assert "expires_at" in d
    # Should not expose artifact paths
    assert "artifact_dir" not in d


def test_render_report_markdown(tmp_path: Path):
    store = _store(tmp_path)
    _create(store)
    store.finish(
        run_id="run-001",
        status=RunStatus.COMPLETE,
        retry_count=0,
        evaluation_result={"outcome": "success"},
        report_json={
            "executive_summary": "Processed 10 rows.",
            "kpi_cards": [{"label": "Rows", "value": 10, "source": "summary.json:kpis"}],
            "top_findings": [],
            "anomaly_table": [],
            "data_quality_warnings": [],
            "business_recommendations": ["Focus on Rows."],
            "confidence_note": "All data is computed.",
            "is_partial": False,
            "revised": False,
            "revision_note": "",
        },
        summary_errors=[],
    )
    md = store.get("run-001").render_report_markdown()
    assert md is not None
    assert "Processed 10 rows." in md
    assert "Rows" in md
    assert "Focus on Rows." in md


def test_render_report_markdown_returns_none_when_no_report(tmp_path: Path):
    store = _store(tmp_path)
    _create(store)
    assert store.get("run-001").render_report_markdown() is None


def test_get_findings_returns_dict(tmp_path: Path):
    store = _store(tmp_path)
    _create(store)
    store.finish(
        run_id="run-001",
        status=RunStatus.COMPLETE,
        retry_count=0,
        evaluation_result={"outcome": "success"},
        report_json={"executive_summary": "Done.", "kpi_cards": [], "top_findings": [],
                     "anomaly_table": [], "data_quality_warnings": [],
                     "business_recommendations": [], "confidence_note": "",
                     "is_partial": False, "revised": False, "revision_note": ""},
        summary_errors=[],
    )
    findings = store.get("run-001").get_findings()
    assert findings is not None
    assert findings["run_id"] == "run-001"
    assert "kpi_cards" in findings
    assert "groundedness" in findings


def test_mark_expired(tmp_path: Path):
    import time
    from datetime import datetime, timezone
    store = _store(tmp_path)
    _create(store, run_id="expired-run")

    # Manually set expires_at to the past.
    with store._connect() as conn:
        past = datetime.fromtimestamp(time.time() - 3600, tz=timezone.utc).isoformat()
        conn.execute("UPDATE runs SET expires_at = ? WHERE run_id = ?", (past, "expired-run"))

    count = store.mark_expired()
    assert count == 1
    assert store.get("expired-run").status == RunStatus.EXPIRED
