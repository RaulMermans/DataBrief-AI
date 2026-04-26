"""Tests for backend.services.evaluator."""
from services.evaluator import classify_execution
from services.sandbox_runner import ArtifactMetadata, SandboxResult


def _make_result(**overrides) -> SandboxResult:
    defaults = dict(
        run_id="test-run",
        status="success",
        exit_code=0,
        stdout="",
        stderr="",
        timed_out=False,
        duration_ms=100,
        artifacts=[],
        error=None,
    )
    defaults.update(overrides)
    return SandboxResult(**defaults)


def test_classify_success():
    result = _make_result(status="success", exit_code=0)
    ev = classify_execution(result)
    assert ev.outcome == "success"
    assert "successfully" in ev.note


def test_classify_recoverable_nonzero_exit():
    result = _make_result(
        status="failed",
        exit_code=1,
        stderr="ValueError: bad data",
        error="Generated analysis exited with an error.",
    )
    ev = classify_execution(result)
    assert ev.outcome == "recoverable"
    assert "1" in ev.note  # exit code in note


def test_classify_unrecoverable_import_policy():
    result = _make_result(
        status="failed",
        exit_code=None,
        error="Generated script imports 'socket' which is not on the approved list for sandbox execution.",
    )
    ev = classify_execution(result)
    assert ev.outcome == "unrecoverable"
    assert "unrecoverable" in ev.note


def test_classify_unrecoverable_syntax_error():
    result = _make_result(
        status="failed",
        exit_code=None,
        error="Generated script has a syntax error: invalid syntax",
    )
    ev = classify_execution(result)
    assert ev.outcome == "unrecoverable"


def test_classify_timeout_no_artifacts():
    result = _make_result(
        status="timeout",
        exit_code=None,
        timed_out=True,
        duration_ms=10000,
        artifacts=[],
        error="Generated analysis exceeded the 10 second timeout.",
    )
    ev = classify_execution(result)
    assert ev.outcome == "unrecoverable"
    assert "timed out" in ev.note.lower()


def test_classify_timeout_with_partial_artifacts():
    artifact = ArtifactMetadata(
        name="summary.json",
        path="/tmp/x/summary.json",
        size_bytes=100,
        content_type="application/json",
        url="/api/runs/x/artifacts/summary.json",
    )
    result = _make_result(
        status="timeout",
        exit_code=None,
        timed_out=True,
        duration_ms=10000,
        artifacts=[artifact],
        error="timeout",
    )
    ev = classify_execution(result)
    assert ev.outcome == "recoverable"
    assert "partial" in ev.note.lower()
