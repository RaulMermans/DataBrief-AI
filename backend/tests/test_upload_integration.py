from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_upload_returns_profile_and_route() -> None:
    response = client.post(
        "/api/upload",
        files={
            "file": (
                "sales.csv",
                b"order_date,customer,revenue\n2026-01-01,Ada,120\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["row_count"] == 1
    assert payload["profile"]["column_count"] == 3
    assert payload["route"]["dataset_type"] == "sales"


def test_upload_rejects_non_csv() -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Upload a CSV file."
