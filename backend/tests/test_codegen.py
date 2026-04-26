from pathlib import Path

from services.codegen import generate_python_script


def test_generate_python_script_has_expected_shape(tmp_path: Path) -> None:
    script = generate_python_script(
        profile={
            "inferred_types": {
                "order_date": "date",
                "customer": "string",
                "revenue": "number",
            }
        },
        route={"dataset_type": "sales", "confidence": 0.9, "explanation": "test"},
        plan={
            "likely_kpis": ["Total revenue"],
            "recommended_charts": ["Line chart of revenue by order_date"],
        },
        input_file_path=tmp_path / "input.csv",
        artifact_dir=tmp_path / "artifacts",
    )

    assert "CONTEXT =" in script.code
    assert '"dataset_type": "sales"' in script.code
    assert '"revenue"' in script.code
    assert "subprocess" not in script.code
    assert "socket" not in script.code
    assert "builtins.__import__" not in script.code  # monkeypatch removed; AST policy enforced pre-execution
    assert "pandas" in script.allowed_imports
