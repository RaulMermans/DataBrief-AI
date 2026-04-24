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

    matched = sorted(tokens.intersection(SALES_SIGNALS))
    has_numeric_measure = any(
        inferred_type in {"integer", "number"}
        for inferred_type in profile.get("inferred_types", {}).values()
    )

    score = len(matched) + (1 if has_numeric_measure and matched else 0)
    if score >= 3:
        confidence = min(0.95, 0.55 + (score * 0.1))
        return DatasetRoute(
            dataset_type="sales",
            confidence=round(confidence, 2),
            explanation=f"Matched sales columns: {', '.join(matched[:5])}.",
        )

    return DatasetRoute(
        dataset_type="generic",
        confidence=0.72 if matched else 0.8,
        explanation=(
            "Only weak sales signals were found; using the generic dataset workflow."
        ),
    )
