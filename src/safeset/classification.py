"""Advisory heuristics; never used to grant permission to export."""

import re
from collections import Counter
from decimal import Decimal, InvalidOperation

from .ingestion import Table

DIRECT = re.compile(
    r"(^|_)(name|email|phone|address|username|dob|identifier)(_|$)|"
    r"(^|_)(student|person|university|account)_(id|number)(_|$)",
    re.I,
)
TEXT = re.compile(r"(^|_)(notes?|comments?|description|feedback|text)(_|$)", re.I)
QUASI = re.compile(r"campus|subject|course|year|gpa|postcode|birth|date|gender", re.I)
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
DATE = re.compile(r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b")
LONG_DIGITS = re.compile(r"(?:\d[ ()+.-]*){7,}")
PLAIN_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?\Z")


def inferred_classification(name: str) -> str:
    if DIRECT.search(name):
        return "direct_identifier"
    if TEXT.search(name):
        return "free_text"
    if QUASI.search(name):
        return "quasi_identifier"
    return "unknown"


def formula_or_control(value: str) -> bool:
    return value.lstrip().startswith(("=", "+", "-", "@")) or any(
        ord(ch) < 32 or ord(ch) == 127 for ch in value
    )


def identifier_shaped(value: str) -> bool:
    return bool(EMAIL.search(value) or DATE.search(value) or LONG_DIGITS.fullmatch(value))


def free_text_shaped(value: str) -> bool:
    return len(value) > 64 or len(value.split()) > 4


def safe_category(value: str) -> bool:
    return (
        bool(value)
        and value == value.strip()
        and not formula_or_control(value)
        and not identifier_shaped(value)
        and not free_text_shaped(value)
    )


def canonical_numeric(
    value: str, bounds: tuple[Decimal, Decimal] | None, max_decimal_places: int
) -> str | None:
    """Check a bounded number and discard non-analytical text formatting."""
    if bounds is None or len(value) > 64 or not PLAIN_NUMBER.fullmatch(value):
        return None
    if "." in value and len(value.partition(".")[2]) > max_decimal_places:
        return None
    number = Decimal(value)
    if not number.is_finite() or not bounds[0] <= number <= bounds[1]:
        return None
    whole, separator, fraction = value.partition(".")
    whole = whole.lstrip("0") or "0"
    fraction = fraction.rstrip("0") if separator else ""
    return whole + (f".{fraction}" if fraction else "")


def inferred_type(values: list[str]) -> str:
    present = [v for v in values if v]
    if not present:
        return "empty"
    try:
        numbers = [Decimal(v) for v in present]
        if not all(n.is_finite() for n in numbers):
            return "text"
        return "integer" if all(n == n.to_integral_value() for n in numbers) else "decimal"
    except InvalidOperation:
        return "text"


def inspect_table(table: Table) -> dict:
    columns = []
    for name in table.columns:
        values = [r[name] for r in table.rows]
        counts = Counter(values)
        flags = []
        if any(identifier_shaped(v) for v in values):
            flags.append("identifier_or_date_shape")
        if any(free_text_shaped(v) or formula_or_control(v) for v in values):
            flags.append("free_text_or_unsafe_cell")
        if values and len(counts) / len(values) > 0.5:
            flags.append("high_cardinality")
        if any(re.search(r"\.\d{3,}", v) for v in values):
            flags.append("precise_number")
        columns.append(
            {
                "column": name,
                "inferred_classification": inferred_classification(name),
                "type": inferred_type(values),
                "cardinality": len(counts),
                "blank_count": values.count(""),
                "categories_below_2": sum(n < 2 for n in counts.values()),
                "flags": flags,
            }
        )
    return {
        "rows": len(table.rows),
        "columns": columns,
        "recommendation": "Classify every field explicitly; drop identifiers and free text; "
        "review necessity, rare groups and numerical precision locally.",
        "warning": "Heuristics are incomplete. This report does not establish anonymity.",
    }
