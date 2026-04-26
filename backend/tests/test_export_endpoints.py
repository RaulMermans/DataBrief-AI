"""Tests for export endpoints and run status endpoint."""
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

_SALES_CSV = b"order_date,customer,revenue\n2026-01-01,Ada,120\n2026-01-02,Grace,90\n"


def _upload() -> dict:
    resp = client.post(
        "/api/upload",
        files={"file": ("sales.csv", _SALES_CSV, "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Run status endpoint
# ---------------------------------------------------------------------------


def test_run_status_returns_known_run():
    payload = _upload()
    run_id = payload["run_id"]
    resp = client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert "status" in data
    assert "filename" in data
    assert "expires_at" in data


def test_run_status_404_for_unknown():
    resp = client.get("/api/runs/no-such-run-id-xyz")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Export: report.md
# ---------------------------------------------------------------------------


def test_export_report_md():
    payload = _upload()
    run_id = payload["run_id"]
    resp = client.get(f"/api/runs/{run_id}/export/report.md")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers.get("content-type", "")
    body = resp.text
    assert "# DataBrief AI" in body
    assert run_id in body


def test_export_report_md_404_for_unknown():
    resp = client.get("/api/runs/unknown-xyz/export/report.md")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Export: findings.json
# ---------------------------------------------------------------------------


def test_export_findings_json():
    payload = _upload()
    run_id = payload["run_id"]
    resp = client.get(f"/api/runs/{run_id}/export/findings.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert "kpi_cards" in data
    assert "top_findings" in data
    assert "groundedness" in data


def test_export_findings_404_for_unknown():
    resp = client.get("/api/runs/unknown-xyz/export/findings.json")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Export: analysis.py
# ---------------------------------------------------------------------------


def test_export_analysis_py():
    payload = _upload()
    run_id = payload["run_id"]
    resp = client.get(f"/api/runs/{run_id}/export/analysis.py")
    assert resp.status_code == 200
    assert "text/x-python" in resp.headers.get("content-type", "")
    assert "CONTEXT" in resp.text
    assert "def main" in resp.text


def test_export_analysis_py_404_for_unknown():
    resp = client.get("/api/runs/unknown-xyz/export/analysis.py")
    assert resp.status_code == 404
