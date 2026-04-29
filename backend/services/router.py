from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SALES_SIGNALS = {
    "amount",
    "customer",
    "customers",
    "date",
    "deal",
    "discount",
    "invoice",
    "order",
    "orders",
    "price",
    "product",
    "quantity",
    "revenue",
    "sale",
    "sales",
    "sku",
    "total",
    "units",
}

ECOMMERCE_SIGNALS = {
    "aov",
    "buyer",
    "cart",
    "category",
    "channel",
    "checkout",
    "coupon",
    "device",
    "discount",
    "gross",
    "item",
    "margin",
    "net",
    "order",
    "orders",
    "payment",
    "price",
    "product",
    "purchase",
    "quantity",
    "refund",
    "return",
    "returned",
    "revenue",
    "sku",
    "status",
    "units",
}

FINANCE_SIGNALS = {
    "account",
    "balance",
    "budget",
    "cash",
    "cost",
    "credit",
    "debit",
    "expense",
    "expenses",
    "income",
    "ledger",
    "margin",
    "payable",
    "payment",
    "profit",
    "receivable",
    "transaction",
}


@dataclass(frozen=True)
class DatasetRoute:
    dataset_type: str
    confidence: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_type": self.dataset_type,
            "confidence": self.confidence,
            "explanation": self.explanation,
        }


def route_dataset(profile: dict[str, Any]) -> DatasetRoute:
    columns = [column.lower() for column in profile.get("inferred_types", {}).keys()]
    tokens = set()
    for column in columns:
        tokens.update(part for part in column.replace("-", "_").split("_") if part)

    ecommerce_matched = sorted(tokens.intersection(ECOMMERCE_SIGNALS))
    finance_matched = sorted(tokens.intersection(FINANCE_SIGNALS))
    sales_matched = sorted(tokens.intersection(SALES_SIGNALS))
    has_numeric_measure = any(
        inferred_type in {"integer", "number"}
        for inferred_type in profile.get("inferred_types", {}).values()
    )
    has_date = any(
        inferred_type == "date"
        for inferred_type in profile.get("inferred_types", {}).values()
    )
    has_order_signal = _has_column(columns, ["order", "order_id", "order_number"])
    has_product_signal = _has_column(columns, ["product", "sku", "item", "category"])
    has_channel_signal = _has_column(columns, ["channel", "device", "payment", "status"])
    has_revenue_signal = _has_column(columns, ["revenue", "amount", "sales", "total", "price", "gross", "net"])
    ecommerce_specific = tokens.intersection(
        {
            "cart",
            "category",
            "channel",
            "checkout",
            "coupon",
            "device",
            "gross",
            "margin",
            "net",
            "payment",
            "refund",
            "return",
            "returned",
            "sku",
            "status",
        }
    )

    ecommerce_score = (
        len(ecommerce_matched)
        + (2 if has_order_signal and has_product_signal else 0)
        + (1 if has_channel_signal else 0)
        + (1 if has_numeric_measure and has_revenue_signal else 0)
        + (1 if has_date and has_order_signal else 0)
    )
    if has_order_signal and has_product_signal and len(ecommerce_specific) >= 2 and ecommerce_score >= 6:
        confidence = min(0.96, 0.58 + (ecommerce_score * 0.06))
        rationale = ecommerce_matched[:6]
        return DatasetRoute(
            dataset_type="ecommerce",
            confidence=round(confidence, 2),
            explanation=(
                "Matched ecommerce transaction signals: "
                f"{', '.join(rationale)}. Orders/products plus revenue or channel fields "
                "fit the ecommerce workflow."
            ),
        )

    finance_score = (
        len(finance_matched)
        + (1 if has_numeric_measure and finance_matched else 0)
        + (1 if has_date and finance_matched else 0)
    )
    if finance_score >= 4:
        confidence = min(0.94, 0.58 + (finance_score * 0.07))
        return DatasetRoute(
            dataset_type="finance",
            confidence=round(confidence, 2),
            explanation=f"Matched finance columns: {', '.join(finance_matched[:6])}.",
        )

    sales_score = len(sales_matched) + (1 if has_numeric_measure and sales_matched else 0)
    if sales_score >= 3:
        confidence = min(0.95, 0.55 + (sales_score * 0.1))
        return DatasetRoute(
            dataset_type="sales",
            confidence=round(confidence, 2),
            explanation=f"Matched sales columns: {', '.join(sales_matched[:5])}.",
        )

    return DatasetRoute(
        dataset_type="generic",
        confidence=0.72 if sales_matched or ecommerce_matched or finance_matched else 0.8,
        explanation=(
            "Only weak domain signals were found; using the generic dataset workflow."
        ),
    )


def _has_column(columns: list[str], tokens: list[str]) -> bool:
    return any(any(token in column for token in tokens) for column in columns)
