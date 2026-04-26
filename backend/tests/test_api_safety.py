"""Tests that public API responses never expose host filesystem paths."""
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.main import app

client = TestClient(app)

_SALES_CSV = b"order_date,customer,revenue\n2026-01-01,Ada,120\n2026-01-02,Grace,90\n"


def _upload_sales():
    return client.post(
        "/api/upload",
        files={"file": ("sales.csv", _SALES_CSV, "text/csv")},
    )


def test_artifacts_have_no_path_field():
    resp = _upload_sales()
    assert resp.status_code == 200
    payload = resp.json()
    for artifact in payload["execution"]["artifacts"]:
        assert "path" not in artifact, (
            f"Artifact '{artifact.get('name')}' exposes a 'path' field in the API response"
        )


def test_artifacts_url_is_relative():
    resp = _upload_sales()
    assert resp.status_code == 200
    for artifact in resp.json()["execution"]["artifacts"]:
        url = artifact.get("url", "")
        assert url.startswith("/api/runs/"), f"Unexpected artifact URL: {url!r}"


def test_response_contains_run_id():
    resp = _upload_sales()
    assert resp.status_code == 200
    payload = resp.json()
    assert "run_id" in payload
    assert len(payload["run_id"]) > 0


def test_no_absolute_paths_in_top_level_response():
    """No value at the top level of the response should be an absolute path."""
    resp = _upload_sales()
    assert resp.status_code == 200
    payload = resp.json()
    for key in ("filename", "run_id"):
        assert payload[key] and not payload[key].startswith("/"), (
            f"Top-level field '{key}' looks like an absolute path: {payload[key]!r}"
        )


def test_summary_validation_present_in_response():
    resp = _upload_sales()
    assert resp.status_code == 200
    assert "summary_validation" in resp.json()
    assert "errors" in resp.json()["summary_validation"]
