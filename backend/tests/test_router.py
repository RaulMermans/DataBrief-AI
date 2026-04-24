from backend.services.router import route_dataset


def test_route_dataset_detects_sales() -> None:
    route = route_dataset(
        {
            "inferred_types": {
                "order_date": "date",
                "customer": "string",
                "product": "string",
                "revenue": "number",
            }
        }
    )

    assert route.dataset_type == "sales"
    assert route.confidence >= 0.75
    assert "sales columns" in route.explanation


def test_route_dataset_defaults_to_generic() -> None:
    route = route_dataset({"inferred_types": {"city": "string", "population": "integer"}})

    assert route.dataset_type == "generic"
    assert route.confidence == 0.8
