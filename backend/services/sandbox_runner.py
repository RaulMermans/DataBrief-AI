from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


RUN_ROOT = Path(tempfile.gettempdir()) / "databrief-ai-runs"
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MEMORY_LIMIT_MB = 512


@dataclass(frozen=True)
class ArtifactMetadata:
    name: str
    path: str
    size_bytes: int
    content_type: str
    url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "url": self.url,
        }


@dataclass(frozen=True)
class SandboxResult:
    run_id: str
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    artifacts: list[ArtifactMetadata]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "error": self.error,
        }


def create_run_directory() -> tuple[str, Path, Path]:
    run_id = uuid4().hex
    run_dir = RUN_ROOT / run_id
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir, artifact_dir


def execute_generated_code(
    code: str,
    run_id: str,
    run_dir: Path,
    artifact_dir: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> SandboxResult:
    script_path = run_dir / "analysis.py"
    script_path.write_text(code, encoding="utf-8")

    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(script_path)],
            cwd=run_dir,
            env=_sandbox_env(),
            text=True,
            input="",
            capture_output=True,
            timeout=timeout_seconds,
            preexec_fn=(
                _resource_limiter(memory_limit_mb, timeout_seconds)
                if os.name == "posix"
                else None
            ),
            check=False,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        artifacts = collect_artifacts(run_id, artifact_dir)
        status = "success" if completed.returncode == 0 else "failed"
        return SandboxResult(
            run_id=run_id,
            status=status,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
            duration_ms=duration_ms,
            artifacts=artifacts,
            error=None if status == "success" else "Generated analysis exited with an error.",
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return SandboxResult(
            run_id=run_id,
            status="timeout",
            exit_code=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            timed_out=True,
            duration_ms=duration_ms,
            artifacts=collect_artifacts(run_id, artifact_dir),
            error=f"Generated analysis exceeded the {timeout_seconds} second timeout.",
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return SandboxResult(
            run_id=run_id,
            status="failed",
            exit_code=None,
            stdout="",
            stderr="",
            timed_out=False,
            duration_ms=duration_ms,
            artifacts=collect_artifacts(run_id, artifact_dir),
            error=f"Sandbox runner failed safely: {exc}",
        )


def collect_artifacts(run_id: str, artifact_dir: Path) -> list[ArtifactMetadata]:
    artifacts: list[ArtifactMetadata] = []
    if not artifact_dir.exists():
        return artifacts

    for path in sorted(item for item in artifact_dir.iterdir() if item.is_file()):
        artifacts.append(
            ArtifactMetadata(
                name=path.name,
                path=str(path),
                size_bytes=path.stat().st_size,
                content_type=_content_type(path),
                url=f"/api/runs/{run_id}/artifacts/{path.name}",
            )
        )
    return artifacts


def resolve_artifact_path(run_id: str, artifact_name: str) -> Path | None:
    if "/" in artifact_name or "\\" in artifact_name:
        return None
    artifact_path = RUN_ROOT / run_id / "artifacts" / artifact_name
    try:
        artifact_path.resolve().relative_to((RUN_ROOT / run_id / "artifacts").resolve())
    except ValueError:
        return None
    if not artifact_path.is_file():
        return None
    return artifact_path


def _sandbox_env() -> dict[str, str]:
    return {
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
    }


def _resource_limiter(memory_limit_mb: int, timeout_seconds: int):
    def limit_resources() -> None:
        try:
            import resource

            memory_bytes = memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            cpu_seconds = timeout_seconds + 1
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        except Exception:
            return

    return limit_resources


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".json":
        return "application/json"
    if suffix == ".csv":
        return "text/csv"
    return "application/octet-stream"
