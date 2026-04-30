from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_EXTERNAL_LIBRARIES = {"pandas", "numpy", "matplotlib", "seaborn"}
ALLOWED_STDLIB_IMPORTS = {
    "collections",
    "csv",
    "datetime",
    "html",
    "json",
    "math",
    "pathlib",
    "statistics",
    "sys",
}


@dataclass(frozen=True)
class GeneratedCode:
    code: str
    allowed_imports: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "allowed_imports": self.allowed_imports,
        }


@dataclass(frozen=True)
class RepairInstruction:
    """Structured description of the repair applied to a failed codegen attempt."""

    failure_type: str
    repair_action: str   # "skip_charts" | "skip_date_analysis" | "minimal_mode" | "none"
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_type": self.failure_type,
            "repair_action": self.repair_action,
            "description": self.description,
        }


def generate_python_script(
    profile: dict[str, Any],
    route: dict[str, Any],
    plan: dict[str, Any],
    input_file_path: str | Path,
    artifact_dir: str | Path,
    *,
    skip_charts: bool = False,
    skip_date_analysis: bool = False,
) -> GeneratedCode:
    dataset_type = route.get("dataset_type", "generic")
    if dataset_type not in {"sales", "ecommerce", "finance", "generic"}:
        dataset_type = "generic"

    inferred_types = profile.get("inferred_types", {})
    columns = list(inferred_types.keys())
    numeric_columns = [
        column
        for column, inferred_type in inferred_types.items()
        if inferred_type in {"integer", "number"}
    ]
    date_columns = (
        []
        if skip_date_analysis
        else [column for column, inferred_type in inferred_types.items() if inferred_type == "date"]
    )
    category_columns = [
        column
        for column, inferred_type in inferred_types.items()
        if inferred_type in {"string", "boolean"}
    ]

    context = {
        "dataset_type": dataset_type,
        "columns": columns,
        "numeric_columns": numeric_columns,
        "date_columns": date_columns,
        "category_columns": category_columns,
        "plan_kpis": plan.get("likely_kpis", []),
        "plan_charts": plan.get("recommended_charts", []),
        "input_file_path": str(input_file_path),
        "artifact_dir": str(artifact_dir),
        "skip_charts": 1 if skip_charts else 0,
    }

    return GeneratedCode(
        code=_SCRIPT_TEMPLATE.replace("__CONTEXT_JSON__", json.dumps(context, indent=2)),
        allowed_imports=sorted(ALLOWED_STDLIB_IMPORTS | ALLOWED_EXTERNAL_LIBRARIES),
    )


# ---------------------------------------------------------------------------
# Repair: deterministic code-repair based on failure type
# ---------------------------------------------------------------------------

# Do not repair these failure types — retrying will not help.
_UNRECOVERABLE_FOR_REPAIR: frozenset[str] = frozenset(
    {"import_policy", "syntax_error", "timeout", "none"}
)

# Map: repair number → (repair_action, skip_charts, skip_date_analysis)
_REPAIR_SEQUENCE: list[tuple[str, bool, bool]] = [
    ("skip_charts", True, False),       # repair 1: skip chart generation
    ("minimal_mode", True, True),       # repair 2: skip charts + date analysis
]


def apply_codegen_repair(
    profile: dict[str, Any],
    route: dict[str, Any],
    plan: dict[str, Any],
    input_file_path: str | Path,
    artifact_dir: str | Path,
    failure_type: str,
    stderr: str,
    repair_attempt: int,
) -> tuple[GeneratedCode, RepairInstruction] | None:
    """Produce a repaired code variant based on *failure_type*.

    Returns ``(GeneratedCode, RepairInstruction)`` if a repair is applicable,
    or ``None`` if the failure is unrecoverable or no further repairs are available.

    Args:
        repair_attempt: 1-indexed repair number (1 = first repair, 2 = second).
    """
    if failure_type in _UNRECOVERABLE_FOR_REPAIR:
        return None

    repair_index = repair_attempt - 1
    if repair_index >= len(_REPAIR_SEQUENCE):
        return None

    repair_action, skip_charts, skip_date_analysis = _REPAIR_SEQUENCE[repair_index]

    # For missing_column failures, also try to remove the offending column.
    modified_profile = dict(profile)
    if failure_type == "missing_column":
        bad_column = _extract_keyerror_column(stderr)
        if bad_column:
            inferred = dict(modified_profile.get("inferred_types", {}))
            inferred.pop(bad_column, None)
            modified_profile = {**modified_profile, "inferred_types": inferred}
            description = f"Removed column '{bad_column}' that caused KeyError; {repair_action}"
        else:
            description = f"Repair {repair_attempt}: {repair_action}"
    elif failure_type == "date_parsing":
        # Force date analysis off regardless of repair sequence position
        skip_date_analysis = True
        description = f"Disabled date analysis that caused parsing error; {repair_action}"
    else:
        description = f"Repair {repair_attempt}: {repair_action} (failure={failure_type})"

    code = generate_python_script(
        modified_profile,
        route,
        plan,
        input_file_path,
        artifact_dir,
        skip_charts=skip_charts,
        skip_date_analysis=skip_date_analysis,
    )
    return code, RepairInstruction(
        failure_type=failure_type,
        repair_action=repair_action,
        description=description,
    )


def _extract_keyerror_column(stderr: str) -> str | None:
    """Try to extract the column name from a KeyError traceback."""
    match = re.search(r"KeyError: ['\"]([^'\"]+)['\"]", stderr)
    return match.group(1) if match else None


_SCRIPT_TEMPLATE = r'''import csv
import datetime
import html
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Import policy is enforced by AST analysis in sandbox_runner before this
# script is executed.  There is no runtime import monkeypatch here because
# stdlib internal lazy imports (e.g. _io, ntpath) would trigger a blanket
# guard and cause spurious failures.

CONTEXT = __CONTEXT_JSON__
INPUT_FILE = Path(CONTEXT["input_file_path"])
ARTIFACT_DIR = Path(CONTEXT["artifact_dir"])
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
SKIP_CHARTS = bool(CONTEXT.get("skip_charts", False))


def main():
    rows = load_csv(INPUT_FILE)
    if not rows:
        raise ValueError("Execution input has no data rows")

    columns = CONTEXT["columns"] or list(rows[0].keys())
    numeric_columns = [column for column in CONTEXT["numeric_columns"] if column in columns]
    date_columns = [column for column in CONTEXT["date_columns"] if column in columns]
    category_columns = [column for column in CONTEXT["category_columns"] if column in columns]

    cleaned_rows = clean_rows(rows, columns)
    duplicate_rows = count_duplicates(cleaned_rows, columns)
    missing = missing_counts(cleaned_rows, columns)
    numeric_summary = summarize_numeric(cleaned_rows, numeric_columns)
    category_summary = summarize_categories(cleaned_rows, category_columns)

    kpis = build_kpis(
        cleaned_rows,
        columns,
        numeric_columns,
        category_columns,
        duplicate_rows,
        missing,
    )
    write_json(
        ARTIFACT_DIR / "summary.json",
        {
            "dataset_type": CONTEXT["dataset_type"],
            "row_count": len(cleaned_rows),
            "column_count": len(columns),
            "duplicate_rows": duplicate_rows,
            "kpis": kpis,
            "numeric_summary": numeric_summary,
            "category_summary": category_summary,
            "plan_kpis": CONTEXT["plan_kpis"],
            "plan_charts": CONTEXT["plan_charts"],
        },
    )
    write_summary_table(ARTIFACT_DIR / "summary_table.csv", kpis)

    chart_count = 0
    if not SKIP_CHARTS:
        chart_count += write_domain_charts(
            cleaned_rows,
            columns,
            numeric_columns,
            date_columns,
            category_columns,
            missing,
        )

    print(f"Processed {len(cleaned_rows)} rows and {len(columns)} columns.")
    print(f"Saved {chart_count} chart artifact(s) to {ARTIFACT_DIR}.")


def load_csv(path):
    if path.suffix.lower() != ".csv":
        raise ValueError("Sandbox execution input must be a CSV file")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV execution input must include headers")
        return [dict(row) for row in reader]


def clean_rows(rows, columns):
    cleaned = []
    for row in rows:
        cleaned.append({column: str(row.get(column, "") or "").strip() for column in columns})
    return cleaned


def count_duplicates(rows, columns):
    seen = set()
    duplicates = 0
    for row in rows:
        row_key = tuple(row.get(column, "") for column in columns)
        if row_key in seen:
            duplicates += 1
        else:
            seen.add(row_key)
    return duplicates


def missing_counts(rows, columns):
    return {column: sum(1 for row in rows if row.get(column, "") == "") for column in columns}


def parse_float(value):
    text = str(value).strip().replace(",", "")
    if text == "":
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isfinite(number):
        return number
    return None


def numeric_values(rows, column):
    return [value for value in (parse_float(row.get(column, "")) for row in rows) if value is not None]


def summarize_numeric(rows, numeric_columns):
    summary = {}
    for column in numeric_columns:
        values = numeric_values(rows, column)
        if values:
            summary[column] = {
                "count": len(values),
                "sum": round(sum(values), 2),
                "mean": round(statistics.fmean(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
            }
    return summary


def summarize_categories(rows, category_columns):
    summary = {}
    for column in category_columns[:3]:
        counts = Counter(row.get(column, "") or "(missing)" for row in rows)
        summary[column] = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10]
    return summary


def build_kpis(rows, columns, numeric_columns, category_columns, duplicate_rows, missing):
    kpis = {}
    dataset_type = CONTEXT["dataset_type"]
    revenue_column = pick_revenue_measure(columns, numeric_columns)
    gross_column = pick_column(columns, ["gross_sales", "gross", "subtotal"], numeric_columns)
    units_column = pick_column(columns, ["quantity", "qty", "units"], numeric_columns)
    price_column = pick_column(columns, ["unit_price", "item_price", "price"], numeric_columns)
    margin_column = pick_column(columns, ["gross_margin", "margin", "profit"], numeric_columns)
    discount_column = pick_column(columns, ["discount", "coupon"], numeric_columns)
    order_column = pick_column(columns, ["order_id", "order", "transaction"])
    category_column = pick_column(columns, ["category", "product_type", "department", "product"])
    channel_column = pick_column(columns, ["channel", "source", "campaign", "medium"])
    device_column = pick_column(columns, ["device", "platform"])
    status_column = pick_column(columns, ["status", "payment_status", "fulfillment_status", "return", "refund", "cancel"])

    if dataset_type == "ecommerce":
        if gross_column:
            gross_values = numeric_values(rows, gross_column)
            if gross_values:
                kpis["Gross sales"] = round(sum(gross_values), 2)
        revenue_values = spend_values(rows, revenue_column, units_column, price_column)
        if revenue_values:
            revenue_label = "Total estimated spend" if price_column and revenue_column == price_column else "Net revenue"
            net_revenue = round(sum(revenue_values), 2)
            kpis[revenue_label] = net_revenue
            order_count = distinct_count(rows, order_column) if order_column else len(rows)
            kpis["Order count"] = order_count
            if order_count:
                kpis["Average order value"] = round(net_revenue / order_count, 2)
        if margin_column:
            margin_values = numeric_values(rows, margin_column)
            if margin_values:
                kpis["Gross margin"] = round(sum(margin_values), 2)
        if units_column:
            units_values = numeric_values(rows, units_column)
            if units_values:
                kpis["Units sold"] = round(sum(units_values), 2)
        if price_column:
            price_values = numeric_values(rows, price_column)
            if price_values:
                kpis["Average item price"] = round(statistics.fmean(price_values), 2)
        if discount_column:
            discount_values = numeric_values(rows, discount_column)
            if discount_values:
                discount_total = sum(discount_values)
                denominator = sum(numeric_values(rows, gross_column)) if gross_column else discount_total + sum(numeric_values(rows, revenue_column) if revenue_column else [])
                if denominator:
                    kpis["Discount rate"] = round((discount_total / denominator) * 100, 2)
        rate = status_rate(rows, status_column, ["return", "returned", "refund", "refunded", "cancel", "cancelled", "canceled"])
        if rate is not None:
            kpis["Return/cancel rate"] = rate
        if category_column:
            kpis[f"Distinct {category_column}"] = distinct_count(rows, category_column)
        if channel_column:
            kpis[f"Distinct {channel_column}"] = distinct_count(rows, channel_column)
        if device_column:
            kpis[f"Distinct {device_column}"] = distinct_count(rows, device_column)
    else:
        measure_column = revenue_column or (numeric_columns[0] if numeric_columns else None)
        if measure_column:
            values = numeric_values(rows, measure_column)
            if values:
                kpis[f"Total {measure_column}"] = round(sum(values), 2)
                kpis[f"Average {measure_column}"] = round(statistics.fmean(values), 2)
        if category_columns:
            column = category_columns[0]
            kpis[f"Distinct {column}"] = distinct_count(rows, column)

    kpis["Rows"] = len(rows)
    kpis["Columns"] = len(columns)
    kpis["Duplicate rows"] = duplicate_rows
    kpis["Missing cells"] = sum(missing.values())
    return kpis


def pick_revenue_measure(columns, numeric_columns):
    tokens = ("net_revenue", "revenue", "sales", "amount", "total", "spend", "price")
    return pick_column(columns, tokens, numeric_columns)


def spend_values(rows, revenue_column, units_column, price_column):
    if revenue_column and price_column and revenue_column == price_column and units_column:
        values = []
        for row in rows:
            price = parse_float(row.get(price_column, ""))
            quantity = parse_float(row.get(units_column, ""))
            if price is not None and quantity is not None:
                values.append(price * quantity)
        return values
    if revenue_column:
        return numeric_values(rows, revenue_column)
    return []


def pick_column(columns, tokens, allowed_columns=None):
    allowed = set(allowed_columns) if allowed_columns is not None else set(columns)
    for column in columns:
        normalized = column.lower()
        if column in allowed and any(token in normalized for token in tokens):
            return column
    return None


def distinct_count(rows, column):
    if not column:
        return 0
    return len({row.get(column, "") for row in rows if row.get(column, "") != ""})


def status_rate(rows, column, tokens):
    if not column or not rows:
        return None
    matches = 0
    for row in rows:
        text = row.get(column, "").lower()
        if any(token in text for token in tokens):
            matches += 1
    return round((matches / len(rows)) * 100, 2)


def write_domain_charts(rows, columns, numeric_columns, date_columns, category_columns, missing):
    chart_count = 0
    dataset_type = CONTEXT["dataset_type"]
    revenue_column = pick_revenue_measure(columns, numeric_columns) or (numeric_columns[0] if numeric_columns else None)
    category_column = pick_column(columns, ["category", "product_type", "department", "product"])
    channel_column = pick_column(columns, ["channel", "source", "campaign", "medium"])
    device_column = pick_column(columns, ["device", "platform"])
    status_column = pick_column(columns, ["status", "payment_status", "fulfillment_status", "return", "refund", "cancel"])
    margin_column = pick_column(columns, ["gross_margin", "margin", "profit"], numeric_columns)

    if dataset_type == "ecommerce":
        if category_column:
            chart_count += write_category_chart(
                ARTIFACT_DIR / f"revenue_by_{safe_name(category_column)}.svg",
                rows,
                category_column,
                revenue_column,
            )
        if channel_column:
            chart_count += write_category_chart(
                ARTIFACT_DIR / f"revenue_by_{safe_name(channel_column)}.svg",
                rows,
                channel_column,
                revenue_column,
            )
        if device_column:
            chart_count += write_category_chart(
                ARTIFACT_DIR / f"revenue_by_{safe_name(device_column)}.svg",
                rows,
                device_column,
                revenue_column,
            )
        if date_columns and revenue_column:
            chart_count += write_time_chart(
                ARTIFACT_DIR / f"revenue_trend_{safe_name(revenue_column)}.svg",
                rows,
                date_columns[0],
                revenue_column,
            )
        if status_column:
            chart_count += write_category_chart(
                ARTIFACT_DIR / f"status_distribution_{safe_name(status_column)}.svg",
                rows,
                status_column,
                None,
            )
        if margin_column and category_column:
            chart_count += write_category_chart(
                ARTIFACT_DIR / f"margin_by_{safe_name(category_column)}.svg",
                rows,
                category_column,
                margin_column,
            )
        chart_count += write_missing_chart(ARTIFACT_DIR / "missing_values.svg", missing)
        return chart_count

    chart_count += write_missing_chart(ARTIFACT_DIR / "missing_values.svg", missing)
    if numeric_columns:
        chart_count += write_histogram_chart(
            ARTIFACT_DIR / f"histogram_{safe_name(numeric_columns[0])}.svg",
            rows,
            numeric_columns[0],
        )
    if category_columns:
        chart_count += write_category_chart(
            ARTIFACT_DIR / f"category_{safe_name(category_columns[0])}.svg",
            rows,
            category_columns[0],
            revenue_column,
        )
    if date_columns and revenue_column:
        chart_count += write_time_chart(
            ARTIFACT_DIR / f"time_{safe_name(revenue_column)}.svg",
            rows,
            date_columns[0],
            revenue_column,
        )
    return chart_count


def write_json(path, payload):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def write_summary_table(path, kpis):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        for metric, value in kpis.items():
            writer.writerow([metric, value])


def write_missing_chart(path, missing):
    values = list(missing.items())
    if not values:
        return 0
    write_bar_svg(path, "Missing Values by Column", values[:10])
    return 1


def write_histogram_chart(path, rows, column):
    values = numeric_values(rows, column)
    if not values:
        return 0
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        buckets = [(str(round(minimum, 2)), len(values))]
    else:
        bucket_count = min(8, max(3, int(math.sqrt(len(values)))))
        width = (maximum - minimum) / bucket_count
        counts = [0 for _ in range(bucket_count)]
        for value in values:
            index = min(bucket_count - 1, int((value - minimum) / width))
            counts[index] += 1
        buckets = []
        for index, count in enumerate(counts):
            start = minimum + (index * width)
            end = start + width
            buckets.append((f"{round(start, 1)}-{round(end, 1)}", count))
    write_bar_svg(path, f"Distribution of {column}", buckets)
    return 1


def write_category_chart(path, rows, category_column, metric_column):
    grouped = defaultdict(float)
    counts = Counter()
    for row in rows:
        label = row.get(category_column, "") or "(missing)"
        counts[label] += 1
        if metric_column:
            grouped[label] += parse_float(row.get(metric_column, "")) or 0
    if metric_column:
        values = sorted(grouped.items(), key=lambda item: item[1], reverse=True)[:10]
        title = f"{metric_column} by {category_column}"
    else:
        values = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10]
        title = f"Rows by {category_column}"
    if not values:
        return 0
    write_bar_svg(path, title, values)
    return 1


def write_time_chart(path, rows, date_column, metric_column):
    grouped = defaultdict(float)
    for row in rows:
        date_value = parse_date(row.get(date_column, ""))
        metric_value = parse_float(row.get(metric_column, ""))
        if date_value and metric_value is not None:
            grouped[date_value.isoformat()] += metric_value
    points = sorted(grouped.items())[:24]
    if len(points) < 2:
        return 0
    write_line_svg(path, f"{metric_column} by {date_column}", points)
    return 1


def parse_date(value):
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text[:10])
    except ValueError:
        pass
    for separator in ("/", "-"):
        parts = text.split(separator)
        if len(parts) != 3:
            continue
        try:
            first, second, third = [int(part) for part in parts]
        except ValueError:
            continue
        if first > 31:
            year, month, day = first, second, third
        else:
            month, day, year = first, second, third
        try:
            return datetime.date(year, month, day)
        except ValueError:
            continue
    return None


def safe_name(value):
    return "".join(character if character.isalnum() else "_" for character in value.lower()).strip("_") or "chart"


def write_bar_svg(path, title, values):
    width = 760
    height = 420
    margin_left = 180
    margin_right = 32
    margin_top = 54
    row_height = 30
    values = [(str(label), float(value)) for label, value in values]
    max_value = max([value for _, value in values] + [1])
    chart_height = max(80, row_height * len(values))
    height = max(height, margin_top + chart_height + 36)
    bars = []
    for index, (label, value) in enumerate(values):
        y = margin_top + index * row_height
        bar_width = int((width - margin_left - margin_right) * (value / max_value)) if max_value else 0
        bars.append(
            f'<text x="12" y="{y + 19}" font-size="12" fill="#354652">{html.escape(label[:32])}</text>'
            f'<rect x="{margin_left}" y="{y + 5}" width="{bar_width}" height="18" fill="#2f6f68" />'
            f'<text x="{margin_left + bar_width + 6}" y="{y + 19}" font-size="12" fill="#354652">{round(value, 2)}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<text x="12" y="30" font-size="18" font-weight="700" fill="#1f2933">{html.escape(title)}</text>'
        + "".join(bars)
        + "</svg>"
    )
    path.write_text(svg, encoding="utf-8")


def write_line_svg(path, title, points):
    width = 760
    height = 420
    margin_left = 56
    margin_right = 28
    margin_top = 58
    margin_bottom = 66
    numeric_points = [(label, float(value)) for label, value in points]
    values = [value for _, value in numeric_points]
    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 1)
    x_span = max(len(numeric_points) - 1, 1)
    coords = []
    for index, (_, value) in enumerate(numeric_points):
        x = margin_left + ((width - margin_left - margin_right) * index / x_span)
        y = margin_top + ((height - margin_top - margin_bottom) * (1 - ((value - min_value) / span)))
        coords.append((x, y))
    path_points = " ".join(f"{round(x, 2)},{round(y, 2)}" for x, y in coords)
    labels = []
    for index, (label, _) in enumerate(numeric_points):
        if index in {0, len(numeric_points) - 1}:
            x, _ = coords[index]
            labels.append(f'<text x="{x}" y="{height - 24}" font-size="11" text-anchor="middle" fill="#52616d">{html.escape(label)}</text>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<text x="12" y="30" font-size="18" font-weight="700" fill="#1f2933">{html.escape(title)}</text>'
        f'<polyline fill="none" stroke="#2f6f68" stroke-width="3" points="{path_points}" />'
        + "".join(f'<circle cx="{x}" cy="{y}" r="4" fill="#2f6f68" />' for x, y in coords)
        + "".join(labels)
        + "</svg>"
    )
    path.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Sandbox execution failed: {exc}", file=sys.stderr)
        raise
'''
