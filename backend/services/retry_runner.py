"""Bounded retry runner.

Wraps ``execute_generated_code`` in a deterministic retry loop capped at
``max_retries`` additional attempts after the first (so at most
``max_retries + 1`` total attempts).

Retry policy (explicit, no open-ended agentic behaviour):
- Stop immediately if the evaluation is ``success`` or ``unrecoverable``.
- Retry if the evaluation is ``recoverable`` and we have not yet exhausted the
  allowed attempt count.
- Each retry re-executes the *same* generated code in a fresh run directory;
  there is no codegen loop here.
- Every attempt (success or failure) is recorded in ``retry_history``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.services.evaluator import ExecutionEvaluation, classify_execution
from backend.services.sandbox_runner import (
    SandboxResult,
    create_run_directory,
    execute_generated_code,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # Maximum additional attempts after the initial failure.


@dataclass
class RetryAttempt:
    """Log entry for a single execution attempt within the retry loop."""

    attempt: int  # 1-indexed
    execution: SandboxResult
    evaluation: ExecutionEvaluation
    reason: str  # Why this attempt was made (e.g. "initial", "retry 1 — recoverable")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "execution": self.execution.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "reason": self.reason,
        }


@dataclass
class RetryResult:
    """Outcome of the full bounded retry loop."""

    final_execution: SandboxResult
    final_evaluation: ExecutionEvaluation
    retry_count: int  # Number of retries performed (0 = succeeded on first try)
    retry_history: list[RetryAttempt] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_execution": self.final_execution.to_dict(),
            "final_evaluation": self.final_evaluation.to_dict(),
            "retry_count": self.retry_count,
            "retry_history": [attempt.to_dict() for attempt in self.retry_history],
        }


def run_with_retry(
    code: str,
    artifact_dir: Path,
    *,
    max_retries: int = MAX_RETRIES,
    timeout_seconds: int = 10,
    memory_limit_mb: int = 512,
) -> RetryResult:
    """Execute *code* in the sandbox, retrying up to *max_retries* times on
    recoverable failures.

    Returns a ``RetryResult`` with the full attempt history.  The caller
    receives the same ``run_id`` and ``artifact_dir`` from the *first*
    successful (or final) attempt — subsequent retries use their own fresh
    run directories so artifacts are never mixed.

    Args:
        code: The Python source to execute.
        artifact_dir: Artifact directory for the *primary* run (attempt 1).
        max_retries: Maximum number of additional attempts (default 2).
        timeout_seconds: Per-attempt timeout forwarded to the sandbox.
        memory_limit_mb: Per-attempt memory limit forwarded to the sandbox.
    """
    history: list[RetryAttempt] = []
    retry_count = 0

    # Primary run directory is already created by the caller; subsequent retry
    # runs need fresh directories so we track the primary run_id separately.
    primary_run_dir = artifact_dir.parent  # run_dir is parent of artifact_dir
    primary_run_id = primary_run_dir.name

    for attempt_number in range(1, max_retries + 2):  # 1 initial + max_retries
        if attempt_number == 1:
            run_id = primary_run_id
            run_dir = primary_run_dir
            current_artifact_dir = artifact_dir
            reason = "initial"
        else:
            run_id, run_dir, current_artifact_dir = create_run_directory()
            reason = f"retry {retry_count} — recoverable failure on previous attempt"

        logger.info(
            "retry_runner: attempt=%d run_id=%s reason=%s",
            attempt_number,
            run_id,
            reason,
        )

        execution = execute_generated_code(
            code=code,
            run_id=run_id,
            run_dir=run_dir,
            artifact_dir=current_artifact_dir,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
        )
        evaluation = classify_execution(execution)

        attempt = RetryAttempt(
            attempt=attempt_number,
            execution=execution,
            evaluation=evaluation,
            reason=reason,
        )
        history.append(attempt)

        logger.info(
            "retry_runner: attempt=%d outcome=%s note=%s",
            attempt_number,
            evaluation.outcome,
            evaluation.note,
        )

        if evaluation.outcome in {"success", "unrecoverable"}:
            # No point retrying.
            break

        if attempt_number > max_retries:
            # Exhausted all allowed attempts.
            logger.warning(
                "retry_runner: exhausted %d retries; final outcome=%s",
                max_retries,
                evaluation.outcome,
            )
            break

        retry_count += 1

    final_attempt = history[-1]
    return RetryResult(
        final_execution=final_attempt.execution,
        final_evaluation=final_attempt.evaluation,
        retry_count=retry_count,
        retry_history=history,
    )
