from io import BytesIO
from dataclasses import replace

from fastapi.testclient import TestClient
from openpyxl import Workbook

import main
from main import app


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
    assert response.json()["error"]["code"] == "unsupported_file"


def test_upload_rejects_oversized_file_with_structured_error(monkeypatch) -> None:
    monkeypatch.setattr(main, "settings", replace(main.settings, max_upload_mb=1))

    response = client.post(
        "/api/upload",
        files={"file": ("large.csv", b"a\n" + (b"x\n" * (1024 * 1024)), "text/csv")},
    )

    assert response.status_code == 413
    payload = response.json()
    assert payload["error"]["code"] == "file_too_large"
    assert "1 MB" in payload["error"]["message"]


def test_upload_ecommerce_routes_and_reports_business_kpis() -> None:
    response = client.post(
        "/api/upload",
        files={
            "file": (
                "orders.csv",
                (
                    b"order_id,order_date,sku,category,channel,device,status,net_revenue,gross_sales,discount_amount,quantity\n"
                    b"o1,2026-01-01,s1,Shoes,Paid,Mobile,completed,100,110,10,1\n"
                    b"o2,2026-01-02,s2,Bags,Organic,Desktop,returned,80,80,0,2\n"
                    b"o3,2026-01-03,s3,Shoes,Paid,Mobile,completed,120,130,10,1\n"
                ),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["route"]["dataset_type"] == "ecommerce"
    assert payload["plan"]["dataset_type"] == "ecommerce"
    kpi_labels = [card["label"] for card in payload["report"]["kpi_cards"]]
    assert "Net revenue" in kpi_labels[:3]
    assert kpi_labels.index("Rows") > kpi_labels.index("Net revenue")
    assert any("revenue_by_category" in artifact["name"] for artifact in payload["execution"]["artifacts"])
