from services.planner import generate_analysis_plan, _first_matching_order_id


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


def test_generate_ecommerce_plan_prioritizes_business_kpis() -> None:
    profile = {
        "inferred_types": {
            "order_id": "string",
            "order_date": "date",
            "category": "string",
            "channel": "string",
            "device": "string",
            "status": "string",
            "net_revenue": "number",
            "gross_sales": "number",
            "discount_amount": "number",
            "quantity": "integer",
        }
    }
    route = {"dataset_type": "ecommerce", "confidence": 0.92, "explanation": "test"}

    plan = generate_analysis_plan(profile, route).to_dict()

    assert plan["dataset_type"] == "ecommerce"
    assert "Order count from order_id" in plan["likely_kpis"]
    assert any("Average order value" in item for item in plan["likely_kpis"])
    assert any("channel" in item.lower() for item in plan["recommended_charts"])
    assert any("return" in item.lower() for item in plan["anomaly_checks"])


def test_generate_ecommerce_plan_includes_purchase_history_spend_kpis() -> None:
    profile = {
        "inferred_types": {
            "purchase_date": "date",
            "customer_id": "string",
            "item_name": "string",
            "category": "string",
            "quantity": "integer",
            "unit_price": "number",
        }
    }
    route = {"dataset_type": "ecommerce", "confidence": 0.9, "explanation": "purchase-history"}

    plan = generate_analysis_plan(profile, route).to_dict()

    assert "Total estimated spend" in plan["likely_kpis"]
    assert "Average item price from unit_price" in plan["likely_kpis"]


def test_amazon_style_plan_no_order_count() -> None:
    profile = {
        "inferred_types": {
            "Order Date": "date",
            "ASIN": "string",
            "Title": "string",
            "Category": "string",
            "Quantity": "integer",
            "Purchase Price Per Unit": "number",
        }
    }
    route = {"dataset_type": "ecommerce", "confidence": 0.85, "explanation": "purchase-history"}

    plan = generate_analysis_plan(profile, route).to_dict()

    kpis_text = " ".join(plan["likely_kpis"])
    assert "Order count" not in kpis_text


def test_amazon_style_plan_has_purchase_line_count() -> None:
    profile = {
        "inferred_types": {
            "Order Date": "date",
            "ASIN": "string",
            "Title": "string",
            "Category": "string",
            "Quantity": "integer",
            "Purchase Price Per Unit": "number",
        }
    }
    route = {"dataset_type": "ecommerce", "confidence": 0.85, "explanation": "purchase-history"}

    plan = generate_analysis_plan(profile, route).to_dict()

    assert "Purchase line count" in plan["likely_kpis"]


def test_order_date_not_selected_as_order_id() -> None:
    assert _first_matching_order_id(["Order Date", "Product", "Revenue"]) is None


def test_transaction_date_not_selected_as_order_id() -> None:
    assert _first_matching_order_id(["Transaction Date", "Amount", "Customer"]) is None


def test_real_order_id_enables_order_metrics() -> None:
    profile = {
        "inferred_types": {
            "order_id": "string",
            "order_date": "date",
            "customer_id": "string",
            "net_revenue": "number",
            "status": "string",
        }
    }
    route = {"dataset_type": "ecommerce", "confidence": 0.95, "explanation": "transactional"}

    plan = generate_analysis_plan(profile, route).to_dict()

    assert any("Order count from" in kpi for kpi in plan["likely_kpis"])


def test_generate_plan_includes_revenue_order_kpis_for_spanish_total() -> None:
    profile = {
        "inferred_types": {
            "ID": "integer",
            "Cliente": "string",
            "Fecha": "date",
            "Total": "number",
            "Pago": "string",
            "Estado": "string",
        },
        "sample_rows": [{"ID": "1", "Cliente": "Ada", "Total": "24,67 €"}],
    }
    route = {"dataset_type": "sales", "dataset_subtype": "transactional_orders"}

    plan = generate_analysis_plan(profile, route).to_dict()

    assert "Total revenue" in plan["likely_kpis"]
    assert "Average order value" in plan["likely_kpis"]
    assert "Order count" in plan["likely_kpis"]
