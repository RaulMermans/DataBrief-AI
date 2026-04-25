"""Execution evaluator.

Classifies a ``SandboxResult`` into one of three outcomes:

- ``success``        — exit code 0, analysis completed normally.
- ``recoverable``    — execution failed but the failure is likely transient
                       or data-related; a retry may help.
- ``unrecoverable``  — import policy violation, syntax error, or timeout with
                       no artifacts; retrying will not fix the root cause.

The evaluator produces a short structured note that is logged and surfaced in
the report payload.  No model calls are made here; the classification is
deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.services.sandbox_runner import SandboxResult


# Keywords in the error field or stderr that indicate an unrecoverable failure.
_UNRECOVERABLE_MARKERS = (
    "not on the approved list for sandbox execution",
    "syntax error",
    "SyntaxError",
    "has a syntax error",
)


@dataclass(frozen=True)
class ExecutionEvaluation:
    """Structured evaluation of a single sandbox execution attempt."""

    outcome: str  # "success" | "recoverable" | "unrecoverable"
    note: str  # Short human-readable summary of what happened.

    def to_dict(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "note": self.note}


def classify_execution(result: SandboxResult) -> ExecutionEvaluation:
    """Classify *result* and return an ``ExecutionEvaluation``.

    Decision logic (deterministic, explicit):

    1. Exit code 0 → success.
    2. Import policy violation or AST syntax error → unrecoverable.
    3. Timeout with no partial artifacts → unrecoverable.
    4. Timeout with partial artifacts → recoverable.
    5. Any other non-zero exit → recoverable.
    """
    if result.status == "success" and result.exit_code == 0:
        artifact_count = len(result.artifacts)
        return ExecutionEvaluation(
            outcome="success",
            note=(
                f"Execution completed successfully in {result.duration_ms} ms "
                f"with {artifact_count} artifact(s)."
            ),
        )

    # Check for unrecoverable markers in the error message and stderr.
    combined_error = " ".join(
        filter(None, [result.error or "", result.stderr or ""])
    )
    for marker in _UNRECOVERABLE_MARKERS:
        if marker.lower() in combined_error.lower():
            return ExecutionEvaluation(
                outcome="unrecoverable",
                note=(
                    f"Execution failed with an unrecoverable error "
                    f"(import policy or syntax): {_truncate(combined_error, 200)}"
                ),
            )

    if result.timed_out:
        if result.artifacts:
            return ExecutionEvaluation(
                outcome="recoverable",
                note=(
                    f"Execution timed out after {result.duration_ms} ms but "
                    f"{len(result.artifacts)} partial artifact(s) were captured. "
                    "A retry may succeed with a smaller dataset."
                ),
            )
        return ExecutionEvaluation(
            outcome="unrecoverable",
            note=(
                f"Execution timed out after {result.duration_ms} ms with no "
                "artifacts. The dataset may be too large for the sandbox timeout."
            ),
        )

    # Non-zero exit — likely a data or runtime error.
    stderr_hint = _truncate(result.stderr or "", 200)
    return ExecutionEvaluation(
        outcome="recoverable",
        note=(
            f"Execution exited with code {result.exit_code}. "
            f"Stderr hint: {stderr_hint or '(none)'}"
        ),
    )


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
