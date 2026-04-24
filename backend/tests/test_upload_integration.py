from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

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
    assert payload["plan"]["dataset_type"] == "sales"
    assert len(payload["plan"]["business_questions"]) == 5
    assert "CONTEXT =" in payload["codegen"]["code"]
    assert payload["execution"]["status"] == "success"
    assert any(
        artifact["name"].endswith(".svg")
        for artifact in payload["execution"]["artifacts"]
    )


def test_upload_accepts_xlsx() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["city", "population", "region"])
    sheet.append(["Madrid", 3223000, "EMEA"])

    buffer = BytesIO()
    workbook.save(buffer)

    response = client.post(
        "/api/upload",
        files={
            "file": (
                "cities.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["row_count"] == 1
    assert payload["route"]["dataset_type"] == "generic"
    assert payload["plan"]["dataset_type"] == "generic"
    assert payload["execution"]["status"] == "success"


def test_upload_rejects_non_csv() -> None:
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Upload a CSV or XLSX file."
