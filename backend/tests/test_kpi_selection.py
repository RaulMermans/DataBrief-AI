from services.planner import generate_analysis_plan
from services.semantic_profile import build_semantic_profile


def test_id_and_reference_excluded_from_primary_kpis() -> None:
    profile = {
        "inferred_types": {
            "ID": "integer",
            "Referencia": "integer",
            "Fecha": "date",
            "Cliente": "string",
            "Total": "number",
            "Pago": "string",
            "Estado": "string",
        },
        "sample_rows": [{"ID": "1", "Referencia": "100", "Total": "24,67 €"}],
    }
    profile["semantic_profile"] = build_semantic_profile(profile).to_dict()
    route = {"dataset_type": "sales", "dataset_subtype": "transactional_orders"}

    plan = generate_analysis_plan(profile, route).to_dict()
    kpis = " ".join(plan["likely_kpis"])

    assert "Total revenue" in plan["likely_kpis"]
    assert "Average order value" in plan["likely_kpis"]
    assert "Average ID" not in kpis
    assert "Total ID" not in kpis
    assert "Referencia" not in kpis
