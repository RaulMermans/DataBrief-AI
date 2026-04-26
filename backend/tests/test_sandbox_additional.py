"""Tests for additional sandbox security checks beyond import allowlist."""
from services.sandbox_runner import (
    create_run_directory,
    execute_generated_code,
    validate_suspicious_patterns,
)


# ---------------------------------------------------------------------------
# validate_suspicious_patterns — static checks
# ---------------------------------------------------------------------------


def test_eval_is_rejected():
    err = validate_suspicious_patterns("eval('print(1)')")
    assert err is not None
    assert "eval" in err


def test_exec_is_rejected():
    err = validate_suspicious_patterns("exec('import os')")
    assert err is not None
    assert "exec" in err


def test_compile_is_rejected():
    err = validate_suspicious_patterns("compile('x=1', '<string>', 'exec')")
    assert err is not None
    assert "compile" in err


def test_dunder_import_is_rejected():
    err = validate_suspicious_patterns("__import__('socket')")
    assert err is not None
    assert "__import__" in err


def test_os_system_is_rejected():
    err = validate_suspicious_patterns("import os\nos.system('ls')")
    assert err is not None
    assert "os.system" in err


def test_os_environ_is_rejected():
    err = validate_suspicious_patterns("import os\nkey = os.environ['SECRET']")
    assert err is not None
    assert "os.environ" in err


def test_os_popen_is_rejected():
    err = validate_suspicious_patterns("import os\nos.popen('cat /etc/passwd')")
    assert err is not None
    assert "os.popen" in err


def test_hardcoded_etc_path_is_rejected():
    err = validate_suspicious_patterns("path = '/etc/passwd'")
    assert err is not None
    assert "/etc/" in err


def test_hardcoded_home_path_is_rejected():
    err = validate_suspicious_patterns("f = open('/home/user/.ssh/id_rsa')")
    assert err is not None


def test_clean_code_passes():
    code = "import csv\nfrom pathlib import Path\nprint('hello')"
    assert validate_suspicious_patterns(code) is None


def test_legitimate_tmp_path_passes():
    """Paths in OS temp dirs are not flagged (generated scripts embed these legitimately)."""
    code = "from pathlib import Path\npath = Path('/tmp/myfile.csv')"
    assert validate_suspicious_patterns(code) is None


# ---------------------------------------------------------------------------
# execute_generated_code — end-to-end rejection
# ---------------------------------------------------------------------------


def test_execute_rejects_eval_call():
    run_id, run_dir, artifact_dir = create_run_directory()
    result = execute_generated_code(
        "eval('print(1)')",
        run_id,
        run_dir,
        artifact_dir,
    )
    assert result.status == "failed"
    assert result.error is not None
    assert "eval" in result.error
    assert result.exit_code is None  # no subprocess spawned


def test_execute_rejects_exec_call():
    run_id, run_dir, artifact_dir = create_run_directory()
    result = execute_generated_code(
        "exec('x=1')",
        run_id,
        run_dir,
        artifact_dir,
    )
    assert result.status == "failed"
    assert result.exit_code is None


def test_execute_rejects_os_environ():
    run_id, run_dir, artifact_dir = create_run_directory()
    result = execute_generated_code(
        "import os\nprint(os.environ['HOME'])",
        run_id,
        run_dir,
        artifact_dir,
    )
    # Note: 'os' itself is not on the import allowlist, so this fails with
    # an import policy error (which also means no subprocess is spawned).
    assert result.status == "failed"
    assert result.exit_code is None
