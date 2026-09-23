"""Fail-closed reconstruction of a source workbook plus approved new results."""

from decimal import Decimal, InvalidOperation

from .bundle import source_digest, validate_bundle
from .classification import canonical_numeric, formula_or_control, safe_category
from .errors import SafetyError
from .ingestion import MAX_COLUMNS, MAX_FIELD, MAX_ROWS, MAX_TABLES, Table, valid_heading
from .policy import parse_policy
from .pseudonyms import valid_id


def _expected(name: str, value: str, rule, bundle: dict) -> str:
    if rule.action == "keep":
        if value not in rule.allowed_values:
            raise SafetyError("Original source violates the bound protection policy.")
        return value
    if rule.action == "code":
        try:
            return bundle["codebooks"][name][value]
        except KeyError:
            raise SafetyError("Original category is absent from the restoration bundle.") from None
    if rule.action == "keep_numeric":
        result = canonical_numeric(value, rule.bounds, rule.max_decimal_places)
        if result is None:
            raise SafetyError("Original source violates the bound protection policy.")
        return result
    if rule.action == "bin":
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise SafetyError("Original source violates the bound protection policy.") from None
        for index, (low, high) in enumerate(rule.bins):
            if low <= number < high or (index == len(rule.bins) - 1 and number == high):
                return rule.labels[index]
    raise SafetyError("Original source violates the bound protection policy.")


def review_reconstruction(source: Table, returned: Table, bundle: dict) -> tuple[str, ...]:
    """Verify all existing values, returning only headings needing user approval."""
    validate_bundle(bundle)
    policy = parse_policy(bundle["policy"])
    original_columns = tuple(bundle["source_columns"])
    protected_columns = tuple(bundle["protected_columns"])
    if source.columns != original_columns or source_digest(source) != bundle["source_digest"]:
        raise SafetyError("Original source does not match the restoration bundle.")
    if returned.columns[: len(protected_columns)] != protected_columns:
        raise SafetyError("Protected workbook schema has changed unexpectedly.")
    new_columns = returned.columns[len(protected_columns) :]
    if (
        len(returned.columns) > MAX_COLUMNS
        or len(set(returned.columns)) != len(returned.columns)
        or any(not valid_heading(c) or c in original_columns for c in new_columns)
        or any(set(row) != set(returned.columns) for row in returned.rows)
    ):
        raise SafetyError("Returned workbook contains unexpected or colliding fields.")
    records = bundle["records"]
    ids = [row["record_id"] for row in returned.rows]
    if any(not valid_id(value) for value in ids) or len(ids) != len(set(ids)):
        raise SafetyError("Returned record IDs are malformed or duplicated.")
    if set(ids) != set(records):
        raise SafetyError("Returned record coverage does not match the bundle.")
    source_by_key = {row[policy.source_key]: row for row in source.rows}
    if len(source_by_key) != len(source.rows) or set(source_by_key) != set(records.values()):
        raise SafetyError("Original source identities do not match the bundle.")
    for row in returned.rows:
        original = source_by_key[records[row["record_id"]]]
        for name in protected_columns[1:]:
            if row[name] != _expected(name, original[name], policy.columns[name], bundle):
                raise SafetyError("A protected source field was changed.")
        for name in new_columns:
            if not safe_category(row[name]) or len(row[name]) > MAX_FIELD:
                raise SafetyError("New result contains unsafe or unsupported spreadsheet text.")
    if any(formula_or_control(value) for row in source.rows for value in row.values()):
        raise SafetyError("Original source contains unsafe spreadsheet text.")
    return new_columns


def reconstruct(
    source: Table, returned: Table, bundle: dict, approved_results: tuple[str, ...]
) -> Table:
    new_columns = review_reconstruction(source, returned, bundle)
    if len(set(approved_results)) != len(approved_results) or set(approved_results) != set(
        new_columns
    ):
        raise SafetyError("Every new result field requires explicit approval.")
    source_by_key = {row[bundle["source_column"]]: row for row in source.rows}
    rows = tuple(
        {
            **source_by_key[bundle["records"][row["record_id"]]],
            **{name: row[name] for name in approved_results},
        }
        for row in returned.rows
    )
    return Table((*source.columns, *approved_results), rows)


def review_analysis_sheets(
    sheets: dict[str, Table], reserved_names: tuple[str, ...], existing_rows: int = 0
) -> tuple[str, ...]:
    """Validate untrusted added worksheets without exposing their cell values."""
    if (
        len(sheets) > MAX_TABLES - len(reserved_names)
        or set(sheets).intersection(reserved_names)
        or any(not valid_heading(name) for name in sheets)
        or existing_rows + sum(len(table.rows) for table in sheets.values()) > MAX_ROWS
    ):
        raise SafetyError("Added analysis worksheet structure is invalid.")
    for table in sheets.values():
        if (
            not table.columns
            or len(table.columns) > MAX_COLUMNS
            or len(set(table.columns)) != len(table.columns)
            or any(not valid_heading(name) for name in table.columns)
            or any(set(row) != set(table.columns) for row in table.rows)
            or any(
                value != "" and (len(value) > MAX_FIELD or not safe_category(value))
                for row in table.rows
                for value in row.values()
            )
        ):
            raise SafetyError("Added analysis worksheet contains unsafe content.")
    return tuple(sheets)


def approved_analysis_sheets(
    sheets: dict[str, Table],
    reserved_names: tuple[str, ...],
    approved: tuple[str, ...],
    existing_rows: int = 0,
) -> dict[str, Table]:
    available = review_analysis_sheets(sheets, reserved_names, existing_rows)
    if len(set(approved)) != len(approved) or set(approved) != set(available):
        raise SafetyError("Every added analysis worksheet requires explicit approval.")
    return {name: sheets[name] for name in available}
