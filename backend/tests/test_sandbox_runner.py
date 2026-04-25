from pathlib import Path

from backend.services.codegen import generate_python_script
from backend.services.sandbox_runner import (
    create_run_directory,
    execute_generated_code,
    validate_imports,
)


def test_execute_generated_code_success(tmp_path: Path) -> None:
    input_path = tmp_path / "sales.csv"
    input_path.write_text(
        "order_date,customer,product,revenue,units\n"
        "2026-01-01,Ada,Widget,1200,12\n"
        "2026-01-02,Grace,Gadget,850,5\n"
        "2026-01-03,Ada,Widget,1420,14\n",
        encoding="utf-8",
    )
    run_id, run_dir, artifact_dir = create_run_directory()
    generated = generate_python_script(
        profile={
            "inferred_types": {
                "order_date": "date",
                "customer": "string",
                "product": "string",
                "revenue": "number",
                "units": "integer",
            }
        },
        route={"dataset_type": "sales", "confidence": 0.95, "explanation": "test"},
        plan={
            "likely_kpis": ["Total revenue", "Average revenue"],
            "recommended_charts": ["Line chart of revenue by order_date"],
        },
        input_file_path=input_path,
        artifact_dir=artifact_dir,
    )

    result = execute_generated_code(generated.code, run_id, run_dir, artifact_dir)

    assert result.status == "success"
    assert result.exit_code == 0
    assert "Processed 3 rows" in result.stdout
    assert any(artifact.name.endswith(".svg") for artifact in result.artifacts)
    assert any(artifact.name == "summary.json" for artifact in result.artifacts)


def test_execute_generated_code_failure_is_structured() -> None:
    run_id, run_dir, artifact_dir = create_run_directory()
    result = execute_generated_code(
        "raise RuntimeError('intentional failure')",
        run_id,
        run_dir,
        artifact_dir,
    )

    assert result.status == "failed"
    assert result.exit_code != 0
    assert result.error == "Generated analysis exited with an error."
    assert "intentional failure" in result.stderr


# ---------------------------------------------------------------------------
# validate_imports — AST policy (no subprocess needed)
# ---------------------------------------------------------------------------


def test_validate_imports_blocks_disallowed_module() -> None:
    error = validate_imports("import socket\nprint('hi')")
    assert error is not None
    assert "socket" in error


def test_validate_imports_blocks_disallowed_from_import() -> None:
    error = validate_imports("from urllib.request import urlopen")
    assert error is not None
    assert "urllib" in error


def test_validate_imports_passes_allowed_code() -> None:
    clean = "import csv\nfrom pathlib import Path\nimport json\n"
    assert validate_imports(clean) is None


def test_validate_imports_reports_syntax_error() -> None:
    error = validate_imports("def broken(:\n    pass")
    assert error is not None
    assert "syntax" in error.lower()


def test_execute_generated_code_rejects_disallowed_import() -> None:
    """validate_imports is called inside execute_generated_code; disallowed
    imports must return a structured failure without spawning a subprocess."""
    run_id, run_dir, artifact_dir = create_run_directory()
    result = execute_generated_code(
        "import socket\nprint('should not run')",
        run_id,
        run_dir,
        artifact_dir,
    )
    assert result.status == "failed"
    assert result.error is not None
    assert "socket" in result.error
    assert result.exit_code is None  # no subprocess was spawned
