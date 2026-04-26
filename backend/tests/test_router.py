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
