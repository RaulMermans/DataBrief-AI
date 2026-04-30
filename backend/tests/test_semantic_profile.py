from services.semantic_profile import build_semantic_profile


def test_spanish_order_columns_infer_roles() -> None:
    profile = {
        "inferred_types": {
            "ID": "integer",
            "Referencia": "string",
            "Cliente": "string",
            "Fecha": "date",
            "Total": "number",
            "Pago": "string",
            "Estado": "string",
            "Entrega": "string",
            "Nuevo cliente": "boolean",
        },
        "sample_rows": [
            {
                "ID": "1",
                "Referencia": "A-1",
                "Cliente": "Ada",
                "Fecha": "2026-01-01",
                "Total": "24,67 €",
                "Pago": "Tarjeta",
                "Estado": "Pagado",
                "Entrega": "Madrid",
                "Nuevo cliente": "sí",
            }
        ],
    }

    semantic = build_semantic_profile(profile).to_dict()

    assert semantic["dataset_subtype"] == "transactional_orders"
    assert semantic["column_roles"]["ID"] == "identifier"
    assert semantic["column_roles"]["Referencia"] == "reference"
    assert semantic["column_roles"]["Cliente"] == "customer"
    assert semantic["column_roles"]["Fecha"] == "date"
    assert semantic["column_roles"]["Total"] == "revenue"
    assert semantic["column_roles"]["Pago"] == "payment_method"
    assert semantic["column_roles"]["Estado"] == "status"
    assert semantic["column_roles"]["Entrega"] == "geography"
    assert semantic["column_roles"]["Nuevo cliente"] == "new_customer"
    assert {"column": "ID", "reason": "identifier"} in semantic["excluded_columns"]
    assert {"column": "Referencia", "reason": "reference"} in semantic["excluded_columns"]


def test_purchase_history_subtype_from_price_quantity() -> None:
    semantic = build_semantic_profile(
        {
            "inferred_types": {
                "purchase_date": "date",
                "item_name": "string",
                "category": "string",
                "quantity": "integer",
                "unit_price": "number",
            },
            "sample_rows": [],
        }
    ).to_dict()

    assert semantic["dataset_subtype"] == "purchase_history"
    assert "estimated_spend" in semantic["usable_metrics"]
