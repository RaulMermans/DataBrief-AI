"""Bounded repair runner.

Executes generated code in the sandbox and, on recoverable failure, applies a
deterministic repair to the codegen inputs before re-generating and re-executing.

Repair policy (explicit, no open-ended agentic behaviour):

1. Execute the initial generated code.
2. If success or unrecoverable → stop.
3. If recoverable → classify the failure type, build a repair instruction,
   re-generate code with modified context (within the same template family),
   re-validate imports and sandbox policy, re-execute.
4. Maximum 2 repair attempts (so at most 3 total executions).
5. Record every attempt (success, failure, repair instruction) in history.

Do not retry on:
- import policy violation
- syntax error
- sandbox policy violation (suspicious patterns)
- timeout without partial artifacts
- repeated timeouts

Codegen inputs (profile, route, plan, input_file_path) are required for
repair-based re-generation.  When omitted, the runner falls back to same-code
retry (backward-compatible with test code that only passes code + artifact_dir).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.services.codegen import RepairInstruction, apply_codegen_repair
from backend.services.evaluator import (
    ExecutionEvaluation,
    classify_execution,
    classify_failure_type,
)
from backend.services.sandbox_runner import (
    SandboxResult,
    create_run_directory,
    execute_generated_code,
)

logger = logging.getLogger(__name__)

MAX_REPAIRS = 2  # Maximum repair-and-retry attempts after the initial execution.
MAX_RETRIES = MAX_REPAIRS  # Alias kept for backward compatibility.


@dataclass
class RetryAttempt:
    """Log entry for a single execution attempt within the repair loop."""

    attempt: int  # 1-indexed
    execution: SandboxResult
    evaluation: ExecutionEvaluation
    reason: str
    repair_instruction: RepairInstruction | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "attempt": self.attempt,
            "execution": self.execution.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "reason": self.reason,
        }
        if self.repair_instruction is not None:
            d["repair_instruction"] = self.repair_instruction.to_dict()
        return d


@dataclass
class RetryResult:
    """Outcome of the full bounded repair loop."""

    final_execution: SandboxResult
    final_evaluation: ExecutionEvaluation
    retry_count: int  # Number of repair attempts performed (0 = succeeded on first try)
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
    # Codegen inputs — required for repair-based re-generation.
    # When omitted the runner falls back to same-code retry.
    profile: dict | None = None,
    route: dict | None = None,
    plan: dict | None = None,
    input_file_path: Path | None = None,
    max_retries: int = MAX_REPAIRS,
    timeout_seconds: int = 10,
    memory_limit_mb: int = 512,
) -> RetryResult:
    """Execute *code* in the sandbox, applying bounded repairs on recoverable failures.

    When *profile*, *route*, *plan*, and *input_file_path* are all provided,
    failures trigger deterministic code repairs (modified codegen context) before
    re-execution.  Otherwise same-code retry is used as a fallback.

    Args:
        code: Initially generated Python source.
        artifact_dir: Artifact directory for the primary run (attempt 1).
        profile: Dataset profile dict (for repair re-generation).
        route: Dataset route dict (for repair re-generation).
        plan: Analysis plan dict (for repair re-generation).
        input_file_path: Path to the execution input CSV (for repair re-generation).
        max_retries: Maximum repair attempts after the initial execution (default 2).
        timeout_seconds: Per-attempt timeout forwarded to the sandbox.
        memory_limit_mb: Per-attempt memory limit forwarded to the sandbox.
    """
    history: list[RetryAttempt] = []
    repair_count = 0
    current_code = code

    primary_run_dir = artifact_dir.parent
    primary_run_id = primary_run_dir.name

    # Repair mode is available only when all codegen inputs are supplied.
    repair_available = all(x is not None for x in (profile, route, plan, input_file_path))

    for attempt_number in range(1, max_retries + 2):  # 1 initial + max_retries
        if attempt_number == 1:
            run_id = primary_run_id
            run_dir = primary_run_dir
            current_artifact_dir = artifact_dir
            reason = "initial"
        else:
            run_id, run_dir, current_artifact_dir = create_run_directory()

        logger.info(
            "repair_runner: attempt=%d run_id=%s reason=%s",
            attempt_number,
            run_id,
            reason,  # defined before use in the loop
        )

        execution = execute_generated_code(
            code=current_code,
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
            "repair_runner: attempt=%d outcome=%s note=%s",
            attempt_number,
            evaluation.outcome,
            evaluation.note,
        )

        if evaluation.outcome in {"success", "unrecoverable"}:
            break

        if attempt_number > max_retries:
            logger.warning(
                "repair_runner: exhausted %d repair(s); final outcome=%s",
                max_retries,
                evaluation.outcome,
            )
            break

        # --- Attempt a repair -----------------------------------------------
        repair_count += 1
        repair_instruction: RepairInstruction | None = None

        if repair_available:
            failure_type = classify_failure_type(execution)
            repair_result = apply_codegen_repair(
                profile=profile,  # type: ignore[arg-type]
                route=route,  # type: ignore[arg-type]
                plan=plan,  # type: ignore[arg-type]
                input_file_path=input_file_path,  # type: ignore[arg-type]
                artifact_dir=current_artifact_dir,
                failure_type=failure_type,
                stderr=execution.stderr or "",
                repair_attempt=repair_count,
            )
            if repair_result is not None:
                repaired_code, repair_instruction = repair_result
                current_code = repaired_code.code
                reason = f"repair {repair_count}: {repair_instruction.repair_action}"
                logger.info(
                    "repair_runner: applied repair=%s description=%s",
                    repair_instruction.repair_action,
                    repair_instruction.description,
                )
                # Attach repair instruction to the *previous* attempt for auditability.
                history[-1].repair_instruction = repair_instruction
            else:
                # No applicable repair; fall back to same-code retry.
                reason = f"retry {repair_count} — no repair available (recoverable)"
        else:
            reason = f"retry {repair_count} — recoverable failure on previous attempt"

    final_attempt = history[-1]
    return RetryResult(
        final_execution=final_attempt.execution,
        final_evaluation=final_attempt.evaluation,
        retry_count=repair_count,
        retry_history=history,
    )
