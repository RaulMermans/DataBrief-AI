from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.semantic_profile import EXCLUDED_ROLES, build_semantic_profile


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
    semantic = profile.get("semantic_profile") or build_semantic_profile(profile).to_dict()
    semantic_plan = _semantic_plan(profile, route, semantic)
    if semantic_plan:
        return semantic_plan

    columns = list(profile.get("inferred_types", {}).keys())
    inferred_types = profile.get("inferred_types", {})
    excluded = _columns_for_roles(semantic, EXCLUDED_ROLES)
    numeric_columns = [
        column for column in _columns_by_type(inferred_types, {"integer", "number"})
        if column not in excluded
    ]
    date_columns = _columns_by_type(inferred_types, {"date"})
    category_columns = _columns_by_type(inferred_types, {"string", "boolean"})

    if dataset_type == "ecommerce":
        return _ecommerce_plan(columns, numeric_columns, date_columns, category_columns)
    if dataset_type == "finance":
        return _finance_plan(columns, numeric_columns, date_columns, category_columns)
    if dataset_type == "sales":
        return _sales_plan(columns, numeric_columns, date_columns, category_columns)

    return _generic_plan(columns, numeric_columns, date_columns, category_columns)


def _semantic_plan(
    profile: dict[str, Any], route: dict[str, Any], semantic: dict[str, Any]
) -> AnalysisPlan | None:
    roles = semantic.get("column_roles", {})
    subtype = route.get("dataset_subtype") or semantic.get("dataset_subtype", "generic")
    dataset_type = route.get("dataset_type", "generic")
    if not roles:
        return None

    revenue = _first_role(roles, ["revenue"])
    date = _first_role(roles, ["date"])
    customer = _first_role(roles, ["customer"])
    new_customer = _first_role(roles, ["new_customer"])
    payment = _first_role(roles, ["payment_method"])
    status = _first_role(roles, ["status"])
    geography = _first_role(roles, ["geography"])
    category = _first_role(roles, ["category", "product"])
    price = _first_role(roles, ["price"])
    quantity = _first_role(roles, ["quantity"])
    order = _first_role(roles, ["order_id"])

    if subtype == "purchase_history" or (dataset_type == "ecommerce" and price and quantity and not revenue):
        return AnalysisPlan(
            dataset_type=dataset_type,
            likely_kpis=_dedupe([
                "Total estimated spend",
                "Total units",
                f"Average item price from {price}" if price else "Average item price",
                f"Order count from {order}" if order else "Purchase line count",
                f"Spend by {category}" if category else None,
                f"Spend by {geography}" if geography else None,
            ]),
            business_questions=[
                "What is the estimated spend across purchases?",
                "Which categories or products account for the most spend?",
                "Which markets or delivery areas concentrate spend?",
                "How many units were purchased?",
                "Where do missing or duplicate records affect trust?",
            ],
            recommended_transformations=_dedupe([
                f"Compute estimated spend as {price} times {quantity}",
                f"Parse {date} into reporting periods" if date else "Add reporting periods if a purchase date exists",
                f"Group products into {category}" if category else "Use product/category fields for merchandising cuts when present",
                "Review duplicate purchase rows",
                "Flag missing purchase fields",
            ]),
            recommended_charts=_dedupe([
                f"Bar chart of estimated spend by {category}" if category else "Bar chart of estimated spend by category",
                f"Bar chart of estimated spend by {geography}" if geography else None,
                f"Line chart of estimated spend by {date}" if date else None,
                "Missing values by column",
            ]),
            anomaly_checks=[
                "Duplicate purchase rows",
                "Missing price, quantity, product, or date values",
                "Negative or zero price and quantity values",
                "Spend outliers by category",
                "Rare or inconsistent product labels",
            ],
        )

    if subtype == "transactional_orders" or (dataset_type == "sales" and revenue):
        return AnalysisPlan(
            dataset_type=dataset_type,
            likely_kpis=_dedupe([
                "Total revenue",
                "Average order value",
                f"Order count from {order}" if order else "Order count",
                f"Unique {customer}" if customer else None,
                f"New customer count from {new_customer}" if new_customer else None,
                f"Payment mix by {payment}" if payment else None,
                f"Status mix by {status}" if status else None,
                f"Revenue by {geography}" if geography else None,
            ]),
            business_questions=[
                "How is revenue trending over time?",
                "What is the average order value?",
                "Which payment methods and statuses dominate orders?",
                "Which customers or markets drive revenue?",
                "Where do missing or duplicate records affect trust?",
            ],
            recommended_transformations=_dedupe([
                f"Parse {date} into reporting periods" if date else "Add a reporting period if a date column is available",
                f"Use {revenue} as the revenue measure",
                f"Normalize {payment} values before grouping" if payment else None,
                f"Normalize {status} values before grouping" if status else None,
                "Review duplicate transaction rows",
            ]),
            recommended_charts=_dedupe([
                f"Line chart of {revenue} by {date}" if date else None,
                f"Bar chart of {revenue} by {payment}" if payment else None,
                f"Bar chart of {revenue} by {status}" if status else None,
                f"Bar chart of {revenue} by {geography}" if geography else None,
                f"Bar chart of {revenue} by {customer}" if customer else None,
                f"Bar chart of {revenue} by {category}" if category else None,
                f"Histogram of {revenue}",
                "Missing values by column",
            ]),
            anomaly_checks=[
                "Duplicate order rows",
                "Missing revenue, customer, status, payment, or date values",
                "Negative or zero revenue values",
                "Revenue outliers by period",
                "Dominant payment, status, or geography segments",
            ],
        )

    return None


def _columns_for_roles(semantic: dict[str, Any], wanted: set[str]) -> set[str]:
    return {
        column for column, role in semantic.get("column_roles", {}).items()
        if role in wanted
    }


def _first_role(roles: dict[str, str], wanted: list[str]) -> str | None:
    for role in wanted:
        for column, column_role in roles.items():
            if column_role == role:
                return column
    return None


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
            f"Average {revenue_column}" if revenue_column else "Average revenue per row",
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


def _ecommerce_plan(
    columns: list[str],
    numeric_columns: list[str],
    date_columns: list[str],
    category_columns: list[str],
) -> AnalysisPlan:
    revenue_column = _first_matching(columns, ["net_revenue", "revenue", "sales", "amount", "total"])
    gross_column = _first_matching(columns, ["gross_sales", "gross", "subtotal"])
    margin_column = _first_matching(columns, ["gross_margin", "margin", "profit"])
    order_column = _first_matching_order_id(columns)
    units_column = _first_matching(columns, ["units", "quantity", "qty"])
    price_column = _first_matching(columns, ["unit_price", "item_price", "price"])
    discount_column = _first_matching(columns, ["discount", "coupon"])
    category_column = _first_matching(columns, ["category", "product_type", "department", "product"])
    channel_column = _first_matching(columns, ["channel", "source", "campaign", "medium"])
    device_column = _first_matching(columns, ["device", "platform"])
    status_column = _first_matching(columns, ["status", "return", "refund", "cancel"])
    date_column = date_columns[0] if date_columns else _first_matching(columns, ["date", "created", "ordered"])

    likely_kpis = _dedupe(
        [
            f"Gross sales from {gross_column}" if gross_column else "Gross sales",
            f"Net revenue from {revenue_column}" if revenue_column else "Net revenue",
            f"Gross margin from {margin_column}" if margin_column else "Gross margin",
            f"Order count from {order_column}" if order_column else None,
            f"Units sold from {units_column}" if units_column else "Units sold",
            "Average order value" if order_column else "Average spend per row",
            "Total estimated spend" if units_column and price_column and not revenue_column else None,
            f"Average item price from {price_column}" if price_column else None,
            f"Return/cancel rate from {status_column}" if status_column else None,
            f"Discount rate from {discount_column}" if discount_column else "Discount rate",
            f"Top categories by {category_column}" if category_column else "Top categories",
            f"Channel performance by {channel_column}" if channel_column else "Acquisition channel performance",
            f"Device performance by {device_column}" if device_column else "Device performance",
            f"Payment/status mix by {status_column}" if status_column else "Payment/status mix",
        ]
    )

    business_questions = [
        "Which categories contribute the most net revenue?",
        "Which acquisition channels and devices drive the strongest revenue?",
        "How are orders, revenue, and average order value trending over time?",
        "Where are returns, cancellations, or discounts reducing realized revenue?",
        "Which payment or order statuses need operational attention?",
    ]

    recommended_transformations = _dedupe(
        [
            f"Parse {date_column} into reporting periods" if date_column else "Add reporting periods if an order date column is available",
            f"Use {revenue_column} as net revenue" if revenue_column else "Identify the best available net revenue measure",
            f"Use {gross_column} and {discount_column} to compute discount rate" if gross_column and discount_column else "Compute discount rate only when gross sales and discount fields exist",
            f"Group products into {category_column}" if category_column else "Use product/category fields for merchandising cuts when present",
            f"Normalize {status_column} values for return/cancel analysis" if status_column else "Normalize fulfillment/payment statuses when present",
        ]
    )

    recommended_charts = _dedupe(
        [
            f"Bar chart of {revenue_column or 'revenue'} by {category_column or 'category'}",
            f"Bar chart of {revenue_column or 'revenue'} by {channel_column or 'channel'}",
            f"Bar chart of {revenue_column or 'revenue'} by {device_column or 'device'}",
            f"Line chart of orders and {revenue_column or 'revenue'} by {date_column or 'period'}",
            f"Status distribution by {status_column}" if status_column else "Status distribution",
            f"Return/cancel distribution by {status_column}" if status_column else "Return/cancel distribution",
            f"Bar chart of {margin_column} by {category_column or 'category'}" if margin_column else "Margin by category if margin is available",
        ]
    )

    anomaly_checks = [
        "Missing order, revenue, product, channel, or status values",
        "Negative net revenue or units sold",
        "High return or cancellation rates",
        "Discount rate spikes by channel or category",
        "Duplicate transaction rows",
    ]

    return AnalysisPlan(
        dataset_type="ecommerce",
        likely_kpis=likely_kpis,
        business_questions=business_questions,
        recommended_transformations=recommended_transformations,
        recommended_charts=recommended_charts,
        anomaly_checks=anomaly_checks,
    )


def _finance_plan(
    columns: list[str],
    numeric_columns: list[str],
    date_columns: list[str],
    category_columns: list[str],
) -> AnalysisPlan:
    amount_column = _first_matching(columns, ["amount", "debit", "credit", "balance", "cost", "expense", "income"])
    account_column = _first_matching(columns, ["account", "category", "department"])
    date_column = date_columns[0] if date_columns else None

    return AnalysisPlan(
        dataset_type="finance",
        likely_kpis=_dedupe(
            [
                f"Total {amount_column}" if amount_column else "Total amount",
                f"Average {amount_column}" if amount_column else "Average transaction value",
                f"Distinct {account_column}" if account_column else "Distinct accounts/categories",
                "Duplicate transaction count",
                "Missing financial fields",
            ]
        ),
        business_questions=[
            "How are financial amounts trending over time?",
            "Which accounts or categories drive the largest totals?",
            "Where do missing or duplicate transactions affect trust?",
            "Which numeric amounts show unusual spikes?",
            "Which categories need closer review?",
        ],
        recommended_transformations=_dedupe(
            [
                f"Parse {date_column} into reporting periods" if date_column else "Add reporting periods if a transaction date exists",
                f"Group by {account_column}" if account_column else "Identify account/category grouping fields",
                "Convert amount fields to numbers",
                "Review duplicate transactions",
                "Flag missing required financial fields",
            ]
        ),
        recommended_charts=_dedupe(
            [
                f"Line chart of {amount_column or 'amount'} by {date_column or 'period'}",
                f"Bar chart of {amount_column or 'amount'} by {account_column or 'category'}",
                f"Histogram of {amount_column}" if amount_column else "Histogram of the primary amount",
                "Missing values by column",
                "Duplicate transaction summary",
            ]
        ),
        anomaly_checks=[
            "Duplicate transactions",
            "Missing amount, account, or date values",
            "Negative or unusually large amounts",
            "High missingness by financial field",
            "Rare or inconsistent account labels",
        ],
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


def _dedupe(items: list[str | None]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


_ORDER_ID_NAMES: frozenset[str] = frozenset({
    "order_id", "orderid", "order_number", "order_no", "order_num",
    "transaction_id", "txn_id",
})


def _first_matching_order_id(columns: list[str]) -> str | None:
    for column in columns:
        normalized = column.lower().replace(" ", "_").replace("-", "_")
        if normalized in _ORDER_ID_NAMES:
            return column
    return None
