from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnalysisPlan:
    dataset_type: str
    likely_kpis: list[str]
    business_questions: list[str]
    recommended_transformations: list[str]
    recommended_charts: list[str]
    anomaly_checks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_type": self.dataset_type,
            "likely_kpis": self.likely_kpis,
            "business_questions": self.business_questions,
            "recommended_transformations": self.recommended_transformations,
            "recommended_charts": self.recommended_charts,
            "anomaly_checks": self.anomaly_checks,
        }


def generate_analysis_plan(
    profile: dict[str, Any], route: dict[str, Any]
) -> AnalysisPlan:
    dataset_type = route["dataset_type"]
    columns = list(profile.get("inferred_types", {}).keys())
    inferred_types = profile.get("inferred_types", {})
    numeric_columns = _columns_by_type(inferred_types, {"integer", "number"})
    date_columns = _columns_by_type(inferred_types, {"date"})
    category_columns = _columns_by_type(inferred_types, {"string", "boolean"})

    if dataset_type == "sales":
        return _sales_plan(columns, numeric_columns, date_columns, category_columns)

    return _generic_plan(columns, numeric_columns, date_columns, category_columns)


def _sales_plan(
    columns: list[str],
    numeric_columns: list[str],
    date_columns: list[str],
    category_columns: list[str],
) -> AnalysisPlan:
    revenue_column = _first_matching(columns, ["revenue", "sales", "amount", "total", "price"])
    units_column = _first_matching(columns, ["units", "quantity", "qty"])
    customer_column = _first_matching(columns, ["customer", "account", "buyer"])
    product_column = _first_matching(columns, ["product", "sku", "item"])
    date_column = date_columns[0] if date_columns else None

    likely_kpis = _dedupe(
        [
            f"Total {revenue_column}" if revenue_column else "Total revenue",
            f"Average {revenue_column}" if revenue_column else "Average order value",
            f"Total {units_column}" if units_column else "Total units sold",
            f"Unique {customer_column}" if customer_column else "Unique customers",
            f"Top {product_column}" if product_column else "Top products",
        ]
    )

    business_questions = [
        "How is sales performance trending over time?",
        "Which products or categories contribute the most revenue?",
        "Which customers or segments drive the most value?",
        "Where are missing or duplicate records affecting analysis quality?",
        "Which numeric measures show unusual spikes or drops?",
    ]

    recommended_transformations = [
        f"Parse {date_column} into reporting periods" if date_column else "Add a reporting period if a date column is available",
        "Standardize product and customer labels before grouping",
        "Convert numeric measure columns to numbers",
        "Flag rows with missing required sales fields",
        "Remove or review duplicate transaction rows",
    ]

    recommended_charts = _dedupe(
        [
            f"Line chart of {revenue_column or 'revenue'} by {date_column or 'period'}",
            f"Bar chart of {revenue_column or 'revenue'} by {product_column or 'product'}",
            f"Bar chart of {revenue_column or 'revenue'} by {customer_column or 'customer segment'}",
            f"Histogram of {numeric_columns[0]}" if numeric_columns else "Histogram of the primary numeric measure",
            "Missing values by column",
        ]
    )

    anomaly_checks = [
        "Duplicate sales rows",
        "Missing revenue, product, customer, or date values",
        "Negative or zero sales amounts",
        "Revenue outliers by period",
        "Sudden changes in units or order counts",
    ]

    return AnalysisPlan(
        dataset_type="sales",
        likely_kpis=likely_kpis,
        business_questions=business_questions,
        recommended_transformations=recommended_transformations,
        recommended_charts=recommended_charts,
        anomaly_checks=anomaly_checks,
    )


def _generic_plan(
    columns: list[str],
    numeric_columns: list[str],
    date_columns: list[str],
    category_columns: list[str],
) -> AnalysisPlan:
    primary_numeric = numeric_columns[0] if numeric_columns else None
    primary_category = category_columns[0] if category_columns else None
    primary_date = date_columns[0] if date_columns else None

    likely_kpis = _dedupe(
        [
            "Row count",
            "Column completeness",
            f"Average {primary_numeric}" if primary_numeric else "Numeric field coverage",
            f"Distinct {primary_category}" if primary_category else "Distinct category counts",
            "Duplicate row count",
        ]
    )

    business_questions = [
        "What fields are available for analysis?",
        "Which columns have missing or low-quality values?",
        "What are the main numeric distributions?",
        "How do key measures vary across categories?",
        "Are there duplicate or unusual records that need review?",
    ]

    recommended_transformations = _dedupe(
        [
            "Normalize column names",
            "Convert typed numeric and date fields",
            "Review columns with missing values",
            f"Group records by {primary_category}" if primary_category else "Identify useful grouping columns",
            f"Create period fields from {primary_date}" if primary_date else "Add time periods if dates exist",
        ]
    )

    recommended_charts = _dedupe(
        [
            "Missing values by column",
            f"Histogram of {primary_numeric}" if primary_numeric else "Column type summary",
            f"Bar chart by {primary_category}" if primary_category else "Top values by category",
            f"Line chart by {primary_date}" if primary_date else "Rows by available time period",
            "Duplicate row summary",
        ]
    )

    anomaly_checks = [
        "Duplicate rows",
        "High missingness by column",
        "Unexpected empty columns",
        "Numeric outliers",
        "Rare categories or inconsistent labels",
    ]

    return AnalysisPlan(
        dataset_type="generic",
        likely_kpis=likely_kpis,
        business_questions=business_questions,
        recommended_transformations=recommended_transformations,
        recommended_charts=recommended_charts,
        anomaly_checks=anomaly_checks,
    )


def _columns_by_type(inferred_types: dict[str, str], types: set[str]) -> list[str]:
    return [column for column, inferred_type in inferred_types.items() if inferred_type in types]


def _first_matching(columns: list[str], tokens: list[str]) -> str | None:
    for column in columns:
        normalized = column.lower()
        if any(token in normalized for token in tokens):
            return column
    return None


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
