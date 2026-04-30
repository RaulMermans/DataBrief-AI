from pathlib import Path

from services.profiler import profile_csv
from services.router import route_dataset


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


def test_route_dataset_detects_ecommerce_transactions() -> None:
    route = route_dataset(
        {
            "inferred_types": {
                "order_id": "string",
                "order_date": "date",
                "sku": "string",
                "category": "string",
                "net_revenue": "number",
                "quantity": "integer",
                "channel": "string",
                "device": "string",
                "status": "string",
            }
        }
    )

    assert route.dataset_type == "ecommerce"
    assert route.confidence >= 0.8
    assert "ecommerce" in route.explanation.lower()


def test_route_dataset_detects_purchase_history_as_ecommerce() -> None:
    route = route_dataset(
        {
            "inferred_types": {
                "purchase_date": "date",
                "customer_id": "string",
                "item_name": "string",
                "category": "string",
                "quantity": "integer",
                "unit_price": "number",
                "city": "string",
            }
        }
    )

    assert route.dataset_type == "ecommerce"
    assert route.confidence >= 0.8
    assert "purchase-history" in route.explanation.lower()


def test_route_dataset_detects_finance() -> None:
    route = route_dataset(
        {
            "inferred_types": {
                "transaction_date": "date",
                "account": "string",
                "debit": "number",
                "credit": "number",
                "balance": "number",
            }
        }
    )

    assert route.dataset_type == "finance"
    assert route.confidence >= 0.75


def test_spanish_order_dataset_routes_non_generic() -> None:
    route = route_dataset(
        {
            "inferred_types": {
                "ID": "integer",
                "Referencia": "string",
                "Cliente": "string",
                "Fecha": "date",
                "Total": "number",
                "Pago": "string",
                "Estado": "string",
                "Entrega": "string",
            },
            "sample_rows": [],
        }
    )

    assert route.dataset_type == "sales"
    assert route.dataset_subtype == "transactional_orders"
    assert route.dataset_type != "generic"


def test_sample_datasets_route_sensibly() -> None:
    expected_routes = {
        "sample_sales.csv": "sales",
        "sample_inventory.csv": "generic",
        "sample_support.csv": "generic",
    }

    examples_dir = Path(__file__).parents[2] / "examples"
    for filename, expected_route in expected_routes.items():
        profile = profile_csv((examples_dir / filename).read_bytes()).to_dict()
        route = route_dataset(profile)

        assert route.dataset_type == expected_route
