from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.normalization import is_parseable_numeric_column, normalize_column_name


BUSINESS_NUMERIC_ROLES = {"revenue", "price", "quantity", "margin", "discount"}
EXCLUDED_ROLES = {"identifier", "reference"}

_ROLE_TOKENS: list[tuple[str, tuple[str, ...]]] = [
    ("new_customer", ("nuevo cliente", "new customer", "new_customer", "first time customer")),
    ("identifier", ("id", "identifier", "uuid")),
    ("reference", ("referencia", "reference", "ref", "sku", "codigo", "code")),
    ("date", ("fecha", "date", "created", "ordered", "purchase date", "transaction date")),
    ("revenue", ("total", "importe", "amount", "revenue", "sales", "gross", "net", "spend")),
    ("price", ("precio", "price", "unit price", "item price")),
    ("quantity", ("cantidad", "quantity", "qty", "units", "unidades")),
    ("customer", ("cliente", "customer", "buyer", "account")),
    ("payment_method", ("pago", "payment", "payment method", "metodo pago", "forma pago")),
    ("status", ("estado", "status", "state", "return", "refund", "cancel")),
    ("geography", ("entrega", "delivery", "country", "region", "city", "state", "market", "pais", "ciudad")),
    ("category", ("categoria", "category", "department", "segment")),
    ("product", ("producto", "product", "item", "articulo", "name")),
    ("margin", ("margen", "margin", "profit")),
    ("discount", ("descuento", "discount", "coupon")),
]


@dataclass(frozen=True)
class SemanticProfile:
    dataset_subtype: str
    confidence: float
    column_roles: dict[str, str]
    usable_metrics: list[str]
    excluded_columns: list[dict[str, str]]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_subtype": self.dataset_subtype,
            "confidence": self.confidence,
            "column_roles": self.column_roles,
            "usable_metrics": self.usable_metrics,
            "excluded_columns": self.excluded_columns,
            "limitations": self.limitations,
        }


def build_semantic_profile(profile: dict[str, Any]) -> SemanticProfile:
    inferred_types = profile.get("inferred_types", {})
    sample_rows = profile.get("sample_rows", [])
    column_roles: dict[str, str] = {}

    for column, inferred_type in inferred_types.items():
        values = [row.get(column, "") for row in sample_rows]
        column_roles[column] = infer_column_role(column, inferred_type, values)

    subtype = _infer_dataset_subtype(column_roles)
    confidence = _confidence(subtype, column_roles)
    usable_metrics = _usable_metrics(column_roles)
    excluded_columns = [
        {"column": column, "reason": role}
        for column, role in column_roles.items()
        if role in EXCLUDED_ROLES
    ]
    limitations = _limitations(column_roles)

    return SemanticProfile(
        dataset_subtype=subtype,
        confidence=confidence,
        column_roles=column_roles,
        usable_metrics=usable_metrics,
        excluded_columns=excluded_columns,
        limitations=limitations,
    )


def infer_column_role(column: str, inferred_type: str, values: list[Any] | None = None) -> str:
    normalized = normalize_column_name(column)
    tokens = set(normalized.split())

    for role, patterns in _ROLE_TOKENS:
        if any(_matches_pattern(normalized, tokens, pattern) for pattern in patterns):
            return role

    if inferred_type == "date":
        return "date"
    if inferred_type in {"string", "boolean"}:
        return "category"
    if values and is_parseable_numeric_column(values):
        return "unknown"
    return "unknown"


def _matches_pattern(normalized: str, tokens: set[str], pattern: str) -> bool:
    pattern = normalize_column_name(pattern)
    if " " in pattern:
        return pattern in normalized
    return pattern in tokens or normalized.endswith(f" {pattern}") or normalized.startswith(f"{pattern} ")


def _infer_dataset_subtype(column_roles: dict[str, str]) -> str:
    roles = set(column_roles.values())
    if {"revenue", "date", "customer"}.issubset(roles) and (
        "payment_method" in roles or "status" in roles
    ):
        return "transactional_orders"
    if "revenue" in roles and "customer" in roles:
        return "sales_pipeline"
    if {"price", "quantity"}.issubset(roles) and ("product" in roles or "category" in roles):
        return "purchase_history"
    if "revenue" in roles and "product" in roles:
        return "ecommerce_orders"
    if "price" in roles and "category" in roles and "date" in roles:
        return "finance_expenses"
    return "generic"


def _confidence(subtype: str, column_roles: dict[str, str]) -> float:
    if subtype == "generic":
        return 0.45
    signal_count = sum(1 for role in column_roles.values() if role != "unknown")
    return round(min(0.95, 0.55 + signal_count * 0.06), 2)


def _usable_metrics(column_roles: dict[str, str]) -> list[str]:
    roles = set(column_roles.values())
    metrics: list[str] = []
    if "revenue" in roles:
        metrics.extend(["revenue", "average_order_value"])
    if "price" in roles and "quantity" in roles:
        metrics.append("estimated_spend")
    if "quantity" in roles:
        metrics.append("total_units")
    if "new_customer" in roles:
        metrics.extend(["new_customer_count", "new_customer_rate"])
    if roles.intersection({"revenue", "price", "quantity"}):
        metrics.append("order_count")
    return _dedupe(metrics)


def _limitations(column_roles: dict[str, str]) -> list[str]:
    roles = set(column_roles.values())
    limitations: list[str] = []
    if "margin" not in roles:
        limitations.append("No margin field detected")
    if "date" not in roles:
        limitations.append("No date field detected")
    if "revenue" not in roles and not {"price", "quantity"}.issubset(roles):
        limitations.append("No revenue or price/quantity spend fields detected")
    if "customer" not in roles:
        limitations.append("No customer field detected")
    return limitations


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
