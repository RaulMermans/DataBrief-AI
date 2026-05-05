from pathlib import Path
import json

from services.codegen import generate_python_script
from services.sandbox_runner import create_run_directory, execute_generated_code


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


def test_generate_python_script_keeps_ecommerce_domain(tmp_path: Path) -> None:
    script = generate_python_script(
        profile={
            "inferred_types": {
                "order_id": "string",
                "order_date": "date",
                "category": "string",
                "channel": "string",
                "device": "string",
                "status": "string",
                "net_revenue": "number",
                "quantity": "integer",
            }
        },
        route={"dataset_type": "ecommerce", "confidence": 0.9, "explanation": "test"},
        plan={
            "likely_kpis": ["Net revenue", "Average order value"],
            "recommended_charts": ["Revenue by category"],
        },
        input_file_path=tmp_path / "input.csv",
        artifact_dir=tmp_path / "artifacts",
    )

    assert '"dataset_type": "ecommerce"' in script.code
    assert "Average order value" in script.code
    assert "write_domain_charts" in script.code


def test_generate_python_script_computes_purchase_history_spend(tmp_path: Path) -> None:
    script = generate_python_script(
        profile={
            "inferred_types": {
                "purchase_date": "date",
                "item_name": "string",
                "quantity": "integer",
                "unit_price": "number",
            }
        },
        route={"dataset_type": "ecommerce", "confidence": 0.9, "explanation": "purchase-history"},
        plan={
            "likely_kpis": ["Total estimated spend", "Average item price"],
            "recommended_charts": [],
        },
        input_file_path=tmp_path / "input.csv",
        artifact_dir=tmp_path / "artifacts",
    )

    assert "spend_values" in script.code
    assert "Total estimated spend" in script.code
    assert "Average item price" in script.code


def test_codegen_avoids_identifier_reference_charts(tmp_path: Path) -> None:
    script = generate_python_script(
        profile={
            "inferred_types": {
                "ID": "integer",
                "Referencia": "integer",
                "Fecha": "date",
                "Total": "number",
                "Cliente": "string",
                "Pago": "string",
                "Estado": "string",
            },
            "sample_rows": [{"ID": "1", "Referencia": "100", "Total": "24,67 €"}],
        },
        route={"dataset_type": "sales", "dataset_subtype": "transactional_orders"},
        plan={"likely_kpis": ["Total revenue"], "recommended_charts": []},
        input_file_path=tmp_path / "input.csv",
        artifact_dir=tmp_path / "artifacts",
    )

    assert '"numeric_columns": [\n    "Total"\n  ]' in script.code
    assert "histogram_id" not in script.code.lower()
    assert "time_id" not in script.code.lower()


def test_purchase_history_spend_executes_as_price_times_quantity(tmp_path: Path) -> None:
    input_path = tmp_path / "purchase.csv"
    input_path.write_text(
        "purchase_date,item_name,quantity,unit_price\n"
        "2026-01-01,Book,2,10\n"
        "2026-01-02,Game,3,20\n",
        encoding="utf-8",
    )
    run_id, run_dir, artifact_dir = create_run_directory()
    generated = generate_python_script(
        profile={
            "inferred_types": {
                "purchase_date": "date",
                "item_name": "string",
                "quantity": "integer",
                "unit_price": "number",
            }
        },
        route={"dataset_type": "ecommerce", "dataset_subtype": "purchase_history"},
        plan={"likely_kpis": ["Total estimated spend"], "recommended_charts": []},
        input_file_path=input_path,
        artifact_dir=artifact_dir,
    )

    result = execute_generated_code(generated.code, run_id, run_dir, artifact_dir)
    summary = json.loads((artifact_dir / "summary.json").read_text(encoding="utf-8"))

    assert result.status == "success"
    assert summary["kpis"]["Total estimated spend"] == 80


def test_generic_numeric_dataset_executes_without_service_constants(tmp_path: Path) -> None:
    input_path = tmp_path / "cities.csv"
    input_path.write_text(
        "city,population,region\n"
        "Madrid,3223000,EMEA\n",
        encoding="utf-8",
    )
    run_id, run_dir, artifact_dir = create_run_directory()
    generated = generate_python_script(
        profile={
            "inferred_types": {
                "city": "string",
                "population": "integer",
                "region": "string",
            }
        },
        route={"dataset_type": "generic", "confidence": 0.6, "explanation": "test"},
        plan={"likely_kpis": ["Average population"], "recommended_charts": []},
        input_file_path=input_path,
        artifact_dir=artifact_dir,
    )

    result = execute_generated_code(generated.code, run_id, run_dir, artifact_dir)
    summary = json.loads((artifact_dir / "summary.json").read_text(encoding="utf-8"))

    assert result.status == "success"
    assert summary["kpis"]["Average population"] == 3223000
