"""Tests for artifact TTL cleanup."""
import time
from pathlib import Path

from services.sandbox_runner import RUN_ROOT, cleanup_expired_runs, create_run_directory


def test_cleanup_removes_old_run_dirs(tmp_path: Path, monkeypatch):
    """Directories older than TTL should be deleted."""
    monkeypatch.setattr("services.sandbox_runner.RUN_ROOT", tmp_path)

    # Create a fresh dir — should NOT be cleaned up.
    fresh = tmp_path / "fresh-run"
    fresh.mkdir()

    # Create a stale dir by setting its mtime to > 1 hour ago.
    stale = tmp_path / "stale-run"
    stale.mkdir()
    old_time = time.time() - 7200  # 2 hours ago
    import os
    os.utime(stale, (old_time, old_time))

    deleted = cleanup_expired_runs(ttl_hours=1)

    assert deleted == 1
    assert not stale.exists()
    assert fresh.exists()


def test_cleanup_zero_when_nothing_expired(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("services.sandbox_runner.RUN_ROOT", tmp_path)

    fresh = tmp_path / "fresh-run"
    fresh.mkdir()

    deleted = cleanup_expired_runs(ttl_hours=24)
    assert deleted == 0
    assert fresh.exists()


def test_cleanup_returns_zero_when_root_missing(tmp_path: Path, monkeypatch):
    absent = tmp_path / "does-not-exist"
    monkeypatch.setattr("services.sandbox_runner.RUN_ROOT", absent)

    deleted = cleanup_expired_runs(ttl_hours=1)
    assert deleted == 0


def test_cleanup_ignores_files_not_dirs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("services.sandbox_runner.RUN_ROOT", tmp_path)

    stale_file = tmp_path / "leftover.json"
    stale_file.write_text("{}")
    import os
    os.utime(stale_file, (time.time() - 7200, time.time() - 7200))

    deleted = cleanup_expired_runs(ttl_hours=1)
    assert deleted == 0
    assert stale_file.exists()
