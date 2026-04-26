"""Tests for backend.services.retry_runner."""
from pathlib import Path

from services.codegen import generate_python_script
from services.retry_runner import MAX_RETRIES, RetryResult, run_with_retry
from services.sandbox_runner import create_run_directory


def _sales_csv(tmp_path: Path) -> Path:
    p = tmp_path / "sales.csv"
    p.write_text(
        "order_date,customer,product,revenue,units\n"
        "2026-01-01,Ada,Widget,1200,12\n"
        "2026-01-02,Grace,Gadget,850,5\n",
        encoding="utf-8",
    )
    return p


def test_retry_succeeds_on_first_attempt(tmp_path: Path) -> None:
    input_path = _sales_csv(tmp_path)
    run_id, run_dir, artifact_dir = create_run_directory()
    generated = generate_python_script(
        profile={"inferred_types": {"order_date": "date", "customer": "string", "revenue": "number", "units": "integer", "product": "string"}},
        route={"dataset_type": "sales"},
        plan={"likely_kpis": [], "recommended_charts": []},
        input_file_path=input_path,
        artifact_dir=artifact_dir,
    )

    result: RetryResult = run_with_retry(code=generated.code, artifact_dir=artifact_dir)

    assert result.final_evaluation.outcome == "success"
    assert result.retry_count == 0
    assert len(result.retry_history) == 1
    assert result.retry_history[0].attempt == 1
    assert result.retry_history[0].reason == "initial"


def test_retry_caps_at_max_retries_on_unrecoverable() -> None:
    """Unrecoverable failure (import policy) must not trigger retries."""
    _run_id, _run_dir, artifact_dir = create_run_directory()

    result: RetryResult = run_with_retry(
        code="import socket\nprint('no')",
        artifact_dir=artifact_dir,
    )

    # No retries: unrecoverable on first attempt
    assert result.retry_count == 0
    assert len(result.retry_history) == 1
    assert result.final_evaluation.outcome == "unrecoverable"


def test_retry_caps_at_max_retries_on_recoverable() -> None:
    """Recoverable failures must retry at most MAX_RETRIES times."""
    _run_id, _run_dir, artifact_dir = create_run_directory()

    result: RetryResult = run_with_retry(
        code="raise RuntimeError('always fails')",
        artifact_dir=artifact_dir,
        max_retries=MAX_RETRIES,
    )

    # Should have attempted 1 initial + MAX_RETRIES retries = MAX_RETRIES+1 total
    assert result.retry_count == MAX_RETRIES
    assert len(result.retry_history) == MAX_RETRIES + 1
    assert result.final_evaluation.outcome == "recoverable"
    # All attempts beyond the first should be labelled as retries
    for attempt in result.retry_history[1:]:
        assert "retry" in attempt.reason


def test_retry_result_to_dict_is_serialisable() -> None:
    _run_id, _run_dir, artifact_dir = create_run_directory()
    result: RetryResult = run_with_retry(
        code="print('ok')",
        artifact_dir=artifact_dir,
    )
    d = result.to_dict()
    assert "final_execution" in d
    assert "final_evaluation" in d
    assert "retry_count" in d
    assert "retry_history" in d
    assert isinstance(d["retry_history"], list)
