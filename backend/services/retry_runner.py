from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.codegen import RepairInstruction, apply_codegen_repair
from services.evaluator import (
    ExecutionEvaluation,
    classify_execution,
    classify_failure_type,
)
from services.sandbox_runner import SandboxResult, execute_generated_code


MAX_REPAIRS = 2
MAX_RETRIES = MAX_REPAIRS


@dataclass(frozen=True)
class RetryAttempt:
    attempt: int
    reason: str
    execution: SandboxResult
    evaluation: ExecutionEvaluation
    failure_type: str
    repair_instruction: RepairInstruction | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "reason": self.reason,
            "execution": self.execution.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "failure_type": self.failure_type,
            "repair_instruction": (
                self.repair_instruction.to_dict()
                if self.repair_instruction is not None
                else None
            ),
        }


@dataclass(frozen=True)
class RetryResult:
    final_execution: SandboxResult
    final_evaluation: ExecutionEvaluation
    retry_count: int
    retry_history: list[RetryAttempt]

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_execution": self.final_execution.to_dict(),
            "final_evaluation": self.final_evaluation.to_dict(),
            "retry_count": self.retry_count,
            "retry_history": [attempt.to_dict() for attempt in self.retry_history],
        }


def run_with_retry(
    code: str,
    artifact_dir: str | Path,
    *,
    profile: dict[str, Any] | None = None,
    route: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    input_file_path: str | Path | None = None,
    max_retries: int = MAX_RETRIES,
) -> RetryResult:
    """Execute generated code with a bounded deterministic repair loop."""
    artifact_path = Path(artifact_dir)
    run_dir = artifact_path.parent
    run_id = run_dir.name

    current_code = code
    retry_history: list[RetryAttempt] = []
    pending_repair: RepairInstruction | None = None

    for index in range(max_retries + 1):
        attempt_number = index + 1
        execution = execute_generated_code(
            current_code,
            run_id=run_id,
            run_dir=run_dir,
            artifact_dir=artifact_path,
        )
        evaluation = classify_execution(execution)
        failure_type = classify_failure_type(execution)
        reason = "initial" if index == 0 else f"retry_{index}"
        retry_history.append(
            RetryAttempt(
                attempt=attempt_number,
                reason=reason,
                execution=execution,
                evaluation=evaluation,
                failure_type=failure_type,
                repair_instruction=pending_repair,
            )
        )
        pending_repair = None

        if evaluation.outcome in {"success", "unrecoverable"}:
            break
        if index >= max_retries:
            break

        repair = _build_repaired_code(
            profile=profile,
            route=route,
            plan=plan,
            input_file_path=input_file_path,
            artifact_dir=artifact_path,
            failure_type=failure_type,
            stderr=execution.stderr,
            repair_attempt=index + 1,
        )
        if repair is not None:
            generated_code, pending_repair = repair
            current_code = generated_code.code

    final_attempt = retry_history[-1]
    return RetryResult(
        final_execution=final_attempt.execution,
        final_evaluation=final_attempt.evaluation,
        retry_count=len(retry_history) - 1,
        retry_history=retry_history,
    )


def _build_repaired_code(
    *,
    profile: dict[str, Any] | None,
    route: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    input_file_path: str | Path | None,
    artifact_dir: Path,
    failure_type: str,
    stderr: str,
    repair_attempt: int,
) -> tuple[Any, RepairInstruction] | None:
    if (
        profile is None
        or route is None
        or plan is None
        or input_file_path is None
    ):
        return None
    return apply_codegen_repair(
        profile=profile,
        route=route,
        plan=plan,
        input_file_path=input_file_path,
        artifact_dir=artifact_dir,
        failure_type=failure_type,
        stderr=stderr,
        repair_attempt=repair_attempt,
    )
