from services.normalization import is_parseable_numeric_column, parse_locale_number
from services.profiler import profile_csv


def test_euro_comma_decimal_parses() -> None:
    assert parse_locale_number("24,67 €") == 24.67
    assert parse_locale_number("1.234,50 €") == 1234.5


def test_detects_parseable_currency_column() -> None:
    assert is_parseable_numeric_column(["24,67 €", "1.234,50 €", ""])


def test_profiler_infers_locale_currency_as_number() -> None:
    profile = profile_csv("Total\n24,67 €\n1.234,50 €\n".encode()).to_dict()

    assert profile["inferred_types"]["Total"] == "number"
