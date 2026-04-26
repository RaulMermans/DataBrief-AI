"""Tests for bounded repair runner — verifies repair-based re-generation."""
from pathlib import Path

import pytest

from services.codegen import apply_codegen_repair, generate_python_script
from services.evaluator import (
    FAILURE_CHART_ERROR,
    FAILURE_DATE_PARSING,
    FAILURE_IMPORT_POLICY,
    FAILURE_MISSING_COLUMN,
    FAILURE_SYNTAX_ERROR,
    FAILURE_TIMEOUT,
    classify_failure_type,
)
from services.retry_runner import MAX_REPAIRS, RetryResult, run_with_retry
from services.sandbox_runner import ArtifactMetadata, SandboxResult, create_run_directory


# ---------------------------------------------------------------------------
# classify_failure_type
# ---------------------------------------------------------------------------


def _make_result(**overrides) -> SandboxResult:
    defaults = dict(
        run_id="t",
        status="failed",
        exit_code=1,
        stdout="",
        stderr="",
        timed_out=False,
        duration_ms=50,
        artifacts=[],
        error="Generated analysis exited with an error.",
    )
    defaults.update(overrides)
    return SandboxResult(**defaults)


def test_classify_import_policy():
    r = _make_result(exit_code=None, error="imports 'socket' which is not on the approved list for sandbox execution.")
    assert classify_failure_type(r) == FAILURE_IMPORT_POLICY


def test_classify_syntax_error():
    r = _make_result(exit_code=None, error="Generated script has a syntax error: invalid syntax")
    assert classify_failure_type(r) == FAILURE_SYNTAX_ERROR


def test_classify_timeout():
    r = _make_result(status="timeout", timed_out=True, exit_code=None, error="timeout")
    assert classify_failure_type(r) == FAILURE_TIMEOUT


def test_classify_missing_column():
    r = _make_result(stderr="KeyError: 'revenue'")
    assert classify_failure_type(r) == FAILURE_MISSING_COLUMN


def test_classify_date_parsing():
    r = _make_result(stderr="ValueError: time data 'bad-date' fromisoformat: invalid format")
    assert classify_failure_type(r) == FAILURE_DATE_PARSING


def test_classify_chart_error():
    r = _make_result(stderr="TypeError in write_bar_svg: expected float")
    assert classify_failure_type(r) == FAILURE_CHART_ERROR


# ---------------------------------------------------------------------------
# apply_codegen_repair
# ---------------------------------------------------------------------------


_PROFILE = {
    "inferred_types": {
        "order_date": "date",
        "customer": "string",
        "revenue": "number",
    }
}
_ROUTE = {"dataset_type": "sales"}
_PLAN = {"likely_kpis": [], "recommended_charts": []}


def test_repair_returns_none_for_import_policy(tmp_path: Path):
    result = apply_codegen_repair(
        _PROFILE, _ROUTE, _PLAN,
        input_file_path=tmp_path / "upload.csv",
        artifact_dir=tmp_path / "artifacts",
        failure_type=FAILURE_IMPORT_POLICY,
        stderr="",
        repair_attempt=1,
    )
    assert result is None


def test_repair_returns_none_for_syntax_error(tmp_path: Path):
    result = apply_codegen_repair(
        _PROFILE, _ROUTE, _PLAN,
        input_file_path=tmp_path / "upload.csv",
        artifact_dir=tmp_path / "artifacts",
        failure_type=FAILURE_SYNTAX_ERROR,
        stderr="",
        repair_attempt=1,
    )
    assert result is None


def test_repair_returns_none_beyond_max_repairs(tmp_path: Path):
    result = apply_codegen_repair(
        _PROFILE, _ROUTE, _PLAN,
        input_file_path=tmp_path / "upload.csv",
        artifact_dir=tmp_path / "artifacts",
        failure_type=FAILURE_CHART_ERROR,
        stderr="",
        repair_attempt=99,  # well beyond max
    )
    assert result is None


def test_repair_1_skips_charts(tmp_path: Path):
    result = apply_codegen_repair(
        _PROFILE, _ROUTE, _PLAN,
        input_file_path=tmp_path / "upload.csv",
        artifact_dir=tmp_path / "artifacts",
        failure_type=FAILURE_CHART_ERROR,
        stderr="",
        repair_attempt=1,
    )
    assert result is not None
    code, instruction = result
    assert "skip_charts" in instruction.repair_action or instruction.repair_action == "skip_charts"
    assert '"skip_charts": 1' in code.code


def test_repair_2_skips_charts_and_date(tmp_path: Path):
    result = apply_codegen_repair(
        _PROFILE, _ROUTE, _PLAN,
        input_file_path=tmp_path / "upload.csv",
        artifact_dir=tmp_path / "artifacts",
        failure_type=FAILURE_CHART_ERROR,
        stderr="",
        repair_attempt=2,
    )
    assert result is not None
    code, instruction = result
    assert '"skip_charts": 1' in code.code
    # date_columns should be empty in the repaired code
    assert '"date_columns": []' in code.code


def test_repair_missing_column_strips_bad_column(tmp_path: Path):
    result = apply_codegen_repair(
        _PROFILE, _ROUTE, _PLAN,
        input_file_path=tmp_path / "upload.csv",
        artifact_dir=tmp_path / "artifacts",
        failure_type=FAILURE_MISSING_COLUMN,
        stderr="KeyError: 'revenue'",
        repair_attempt=1,
    )
    assert result is not None
    code, instruction = result
    assert "revenue" not in code.code or '"revenue"' not in code.code.split("CONTEXT")[1][:500]


def test_repair_date_parsing_clears_date_columns(tmp_path: Path):
    result = apply_codegen_repair(
        _PROFILE, _ROUTE, _PLAN,
        input_file_path=tmp_path / "upload.csv",
        artifact_dir=tmp_path / "artifacts",
        failure_type=FAILURE_DATE_PARSING,
        stderr="fromisoformat error",
        repair_attempt=1,
    )
    assert result is not None
    code, instruction = result
    assert '"date_columns": []' in code.code


# ---------------------------------------------------------------------------
# run_with_retry — repair-enabled mode
# ---------------------------------------------------------------------------


def _sales_csv(tmp_path: Path) -> Path:
    p = tmp_path / "sales.csv"
    p.write_text(
        "order_date,customer,revenue\n2026-01-01,Ada,120\n2026-01-02,Grace,90\n",
        encoding="utf-8",
    )
    return p


def test_repair_runner_succeeds_first_attempt(tmp_path: Path):
    input_path = _sales_csv(tmp_path)
    _run_id, _run_dir, artifact_dir = create_run_directory()
    code = generate_python_script(
        profile={"inferred_types": {"order_date": "date", "customer": "string", "revenue": "number"}},
        route={"dataset_type": "sales"},
        plan={"likely_kpis": [], "recommended_charts": []},
        input_file_path=input_path,
        artifact_dir=artifact_dir,
    ).code

    result = run_with_retry(
        code=code,
        artifact_dir=artifact_dir,
        profile={"inferred_types": {"order_date": "date", "customer": "string", "revenue": "number"}},
        route={"dataset_type": "sales"},
        plan={"likely_kpis": [], "recommended_charts": []},
        input_file_path=input_path,
    )
    assert result.final_evaluation.outcome == "success"
    assert result.retry_count == 0
    assert len(result.retry_history) == 1


def test_repair_runner_no_repair_on_unrecoverable():
    _run_id, _run_dir, artifact_dir = create_run_directory()
    result = run_with_retry(
        code="import socket\nprint('no')",
        artifact_dir=artifact_dir,
        max_retries=MAX_REPAIRS,
    )
    assert result.final_evaluation.outcome == "unrecoverable"
    assert result.retry_count == 0
    assert len(result.retry_history) == 1


def test_repair_runner_caps_at_max_repairs():
    _run_id, _run_dir, artifact_dir = create_run_directory()
    result = run_with_retry(
        code="raise RuntimeError('always fails')",
        artifact_dir=artifact_dir,
        max_retries=MAX_REPAIRS,
    )
    assert result.retry_count == MAX_REPAIRS
    assert len(result.retry_history) == MAX_REPAIRS + 1


def test_repair_attempt_with_codegen_inputs_skips_charts_on_failure(tmp_path: Path):
    """A recoverable failure with codegen inputs should produce a skip_charts repair."""
    input_path = _sales_csv(tmp_path)
    _run_id, _run_dir, artifact_dir = create_run_directory()

    # Force failure on every attempt.
    bad_code = "raise RuntimeError('chart failed')"

    result = run_with_retry(
        code=bad_code,
        artifact_dir=artifact_dir,
        profile={"inferred_types": {"order_date": "date", "revenue": "number"}},
        route={"dataset_type": "sales"},
        plan={"likely_kpis": [], "recommended_charts": []},
        input_file_path=input_path,
        max_retries=MAX_REPAIRS,
    )
    # Repair was applied but still fails (bad_code cannot be fixed by repair)
    assert result.retry_count > 0
    # At least one attempt should have a repair instruction attached
    repaired_attempts = [a for a in result.retry_history if a.repair_instruction is not None]
    assert len(repaired_attempts) >= 1


def test_retry_result_serialises():
    _run_id, _run_dir, artifact_dir = create_run_directory()
    result = run_with_retry(code="print('ok')", artifact_dir=artifact_dir)
    d = result.to_dict()
    assert "final_execution" in d
    assert "final_evaluation" in d
    assert "retry_count" in d
    assert "retry_history" in d
