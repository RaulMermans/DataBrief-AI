from backend.services.planner import generate_analysis_plan


def test_generate_sales_plan_is_structured_and_grounded() -> None:
    profile = {
        "inferred_types": {
            "order_date": "date",
            "customer": "string",
            "product": "string",
            "revenue": "number",
        }
    }
    route = {"dataset_type": "sales", "confidence": 0.95, "explanation": "test"}

    plan = generate_analysis_plan(profile, route).to_dict()

    assert plan["dataset_type"] == "sales"
    assert "Total revenue" in plan["likely_kpis"]
    assert len(plan["business_questions"]) == 5
    assert any("order_date" in item for item in plan["recommended_transformations"])
    assert len(plan["recommended_charts"]) >= 5
    assert len(plan["anomaly_checks"]) == 5


def test_generate_generic_plan_is_structured() -> None:
    profile = {
        "inferred_types": {
            "city": "string",
            "population": "integer",
            "region": "string",
        }
    }
    route = {"dataset_type": "generic", "confidence": 0.8, "explanation": "test"}

    plan = generate_analysis_plan(profile, route).to_dict()

    assert plan["dataset_type"] == "generic"
    assert "Row count" in plan["likely_kpis"]
    assert len(plan["business_questions"]) == 5
    assert any("population" in item for item in plan["recommended_charts"])
