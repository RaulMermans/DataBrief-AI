from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


# ---------------------------------------------------------------------------
# AST-based import policy
# ---------------------------------------------------------------------------
# These are the ONLY top-level module names the generated script is allowed to
# import.  Stdlib internal sub-modules (e.g. _io, ntpath) are excluded from
# this list intentionally: they must not appear as explicit imports in
# generated code.  The policy is enforced by static AST analysis BEFORE any
# subprocess is spawned; there is no runtime monkeypatch.
# ---------------------------------------------------------------------------
_ALLOWED_TOP_LEVEL_IMPORTS: frozenset[str] = frozenset(
    {
        # stdlib used by the template
        "builtins",
        "collections",
        "csv",
        "datetime",
        "html",
        "json",
        "math",
        "pathlib",
        "statistics",
        "sys",
        # approved external libraries
        "pandas",
        "numpy",
        "matplotlib",
        "seaborn",
    }
)


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
        # path is intentionally excluded — never expose host filesystem paths in API responses.
        return {
            "name": self.name,
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


def validate_imports(code: str) -> str | None:
    """Return an error message if *code* imports a disallowed module, else None.

    Parses the script with the stdlib ``ast`` module and inspects every
    ``import`` and ``from … import`` statement at any nesting level.  Only the
    root (top-level) module name is checked so that sub-package imports such as
    ``from pathlib import Path`` continue to work as long as ``pathlib`` is
    allowed.

    This replaces the previous ``builtins.__import__`` monkeypatch which was
    brittle because stdlib internal lazy imports (e.g. ``_io``, ``ntpath``)
    triggered the guard and caused spurious failures.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"Generated script has a syntax error: {exc}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root not in _ALLOWED_TOP_LEVEL_IMPORTS:
                    return (
                        f"Generated script imports '{root}' which is not on the"
                        " approved list for sandbox execution."
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # absolute import only
                root = node.module.split(".", 1)[0]
                if root not in _ALLOWED_TOP_LEVEL_IMPORTS:
                    return (
                        f"Generated script imports from '{root}' which is not on"
                        " the approved list for sandbox execution."
                    )
    return None


# ---------------------------------------------------------------------------
# Additional static safety checks (beyond import allowlist)
# ---------------------------------------------------------------------------
# These checks look for patterns that shouldn't appear in generated analysis
# code even if the author of the code has only allowed imports.
# NOTE: true production hardening requires OS-level isolation (container/
# network namespace/seccomp). These checks are a defence-in-depth layer only.
# ---------------------------------------------------------------------------

_FORBIDDEN_BUILTINS: frozenset[str] = frozenset({"eval", "exec", "compile", "__import__"})
_FORBIDDEN_OS_ATTRS: frozenset[str] = frozenset(
    {"system", "popen", "execv", "execve", "execvp", "execvpe", "fork",
     "environ", "getenv", "putenv", "unsetenv"}
)
_SUSPICIOUS_PATH_PREFIXES: tuple[str, ...] = (
    # System config / sensitive dirs.  Deliberately excludes /tmp/ and
    # /var/folders/ (macOS temp) since generated scripts legitimately embed
    # those paths for input and artifact access.
    "/etc/",
    "/root/",
    "/home/",
    "/proc/",
    "/sys/",
    "C:\\Windows\\",
    "C:\\Users\\",
    "C:\\Program Files",
)


def validate_suspicious_patterns(code: str) -> str | None:
    """Return an error message if *code* contains dangerous patterns beyond import policy.

    Checks (static AST analysis only, no execution):
    - Calls to eval / exec / compile / __import__
    - Access to os.system, os.popen, os.environ, os.execv*, os.fork, os.getenv
    - Hardcoded absolute paths pointing at sensitive system locations
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"Generated script has a syntax error: {exc}"

    for node in ast.walk(tree):
        # Bare calls: eval(...), exec(...), compile(...), __import__(...)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_BUILTINS:
                return (
                    f"Generated script calls '{func.id}' which is not allowed "
                    "in sandbox execution."
                )

        # Attribute access: os.system(...), os.environ[...], etc.
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                if node.attr in _FORBIDDEN_OS_ATTRS:
                    return (
                        f"Generated script accesses 'os.{node.attr}' which is "
                        "not allowed in sandbox execution."
                    )

        # Hardcoded absolute paths pointing at sensitive locations
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            if any(val.startswith(prefix) for prefix in _SUSPICIOUS_PATH_PREFIXES):
                return (
                    f"Generated script contains a suspicious hardcoded path: "
                    f"'{val[:60]}'"
                )

    return None


def execute_generated_code(
    code: str,
    run_id: str,
    run_dir: Path,
    artifact_dir: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> SandboxResult:
    # --- AST import check (pre-execution, no subprocess needed) -------------
    import_error = validate_imports(code)
    if import_error:
        return SandboxResult(
            run_id=run_id,
            status="failed",
            exit_code=None,
            stdout="",
            stderr="",
            timed_out=False,
            duration_ms=0,
            artifacts=[],
            error=import_error,
        )

    # --- Additional suspicious-pattern check --------------------------------
    pattern_error = validate_suspicious_patterns(code)
    if pattern_error:
        return SandboxResult(
            run_id=run_id,
            status="failed",
            exit_code=None,
            stdout="",
            stderr="",
            timed_out=False,
            duration_ms=0,
            artifacts=[],
            error=pattern_error,
        )

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
    # NOTE: This environment strips most host variables and prevents user-site
    # packages from loading.  It does NOT block network access at the OS level
    # (no network namespace / seccomp / iptables rules).  The primary defence
    # against unexpected network use is the AST import policy: socket, urllib,
    # requests, httpx, etc. are not on the approved import list and will be
    # rejected before the subprocess starts.
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


def cleanup_expired_runs(ttl_hours: int) -> int:
    """Delete run directories older than *ttl_hours*. Returns the number of deleted dirs."""
    if not RUN_ROOT.exists():
        return 0
    cutoff = time.time() - (ttl_hours * 3600)
    deleted = 0
    for run_dir in RUN_ROOT.iterdir():
        if not run_dir.is_dir():
            continue
        try:
            if run_dir.stat().st_mtime < cutoff:
                shutil.rmtree(run_dir)
                deleted += 1
        except (OSError, PermissionError):
            pass
    return deleted


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".json":
        return "application/json"
    if suffix == ".csv":
        return "text/csv"
    return "application/octet-stream"
