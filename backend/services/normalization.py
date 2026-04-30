from __future__ import annotations

import re
import unicodedata
from typing import Any


_MOJIBAKE_REPLACEMENTS = {
    "Ã¡": "á",
    "Ã©": "é",
    "Ã­": "í",
    "Ã³": "ó",
    "Ãº": "ú",
    "Ã±": "ñ",
    "Ã": "Á",
    "Ã‰": "É",
    "Ã": "Í",
    "Ã“": "Ó",
    "Ãš": "Ú",
    "Ã‘": "Ñ",
    "Â€": "€",
    "Â£": "£",
    "Â¥": "¥",
    "Â": "",
}

_CURRENCY_AND_SPACE_RE = re.compile(r"[\s\u00a0€$£¥]")
_NUMERIC_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


def clean_mojibake(value: str) -> str:
    cleaned = value
    for bad, good in _MOJIBAKE_REPLACEMENTS.items():
        cleaned = cleaned.replace(bad, good)
    return cleaned


def normalize_column_name(value: str) -> str:
    text = clean_mojibake(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_locale_number(value: Any) -> float | None:
    text = clean_mojibake(str(value or "")).strip()
    if not text:
        return None

    text = _CURRENCY_AND_SPACE_RE.sub("", text)
    text = re.sub(r"[^0-9,.\-+]", "", text)
    if text in {"", "+", "-"}:
        return None

    comma = text.rfind(",")
    dot = text.rfind(".")
    if comma != -1 and dot != -1:
        if comma > dot:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif comma != -1:
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) in {1, 2}:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    elif dot != -1:
        parts = text.split(".")
        if len(parts) > 2 and len(parts[-1]) == 3:
            text = text.replace(".", "")

    if not _NUMERIC_RE.match(text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def is_parseable_numeric_column(values: list[Any], *, threshold: float = 0.8) -> bool:
    non_empty = [value for value in values if str(value or "").strip()]
    if not non_empty:
        return False
    parsed = sum(1 for value in non_empty if parse_locale_number(value) is not None)
    return (parsed / len(non_empty)) >= threshold
