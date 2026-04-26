from io import BytesIO

import pytest
from openpyxl import Workbook

from services.profiler import profile_csv, profile_xlsx


def test_profile_csv_returns_core_dataset_profile() -> None:
    csv_bytes = (
        b"date,product,revenue,units,region\n"
        b"2026-01-01,Widget,100.50,2,North\n"
        b"2026-01-02,Gadget,,1,South\n"
        b"2026-01-02,Gadget,,1,South\n"
    )

    profile = profile_csv(csv_bytes).to_dict()

    assert profile["row_count"] == 3
    assert profile["column_count"] == 5
    assert profile["inferred_types"]["date"] == "date"
    assert profile["inferred_types"]["revenue"] == "number"
    assert profile["missing_percent_by_column"]["revenue"] == 66.67
    assert profile["duplicate_rows"] == 1
    assert len(profile["sample_rows"]) == 3
    assert "1 duplicate row(s) detected" in profile["warnings"]


def test_profile_csv_rejects_empty_file() -> None:
    with pytest.raises(ValueError, match="empty"):
        profile_csv(b"")


def test_profile_xlsx_returns_core_dataset_profile() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["order_date", "customer", "revenue", "units"])
    sheet.append(["2026-01-01", "Ada", 120.5, 2])
    sheet.append(["2026-01-02", "Grace", None, 1])

    buffer = BytesIO()
    workbook.save(buffer)

    profile = profile_xlsx(buffer.getvalue()).to_dict()

    assert profile["row_count"] == 2
    assert profile["column_count"] == 4
    assert profile["inferred_types"]["order_date"] == "date"
    assert profile["inferred_types"]["revenue"] == "number"
    assert profile["missing_percent_by_column"]["revenue"] == 50.0
    assert profile["duplicate_rows"] == 0
