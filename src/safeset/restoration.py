"""Exact local restoration of authorised result columns."""

from .classification import formula_or_control
from .errors import SafetyError
from .ingestion import Table, valid_heading
from .mapping import validate_mapping
from .pseudonyms import valid_id


def restore(analysed: Table, mapping: dict, result_columns: tuple[str, ...]) -> Table:
    validate_mapping(mapping)
    source_key = mapping["source_column"]
    if len(set(result_columns)) != len(result_columns) or any(
        not valid_heading(c) or c in {"record_id", source_key} for c in result_columns
    ):
        raise SafetyError("Result-column allowlist is invalid or collides with an identity field.")
    expected = {"record_id", *result_columns}
    if (
        len(set(analysed.columns)) != len(analysed.columns)
        or set(analysed.columns) != expected
        or any(set(row) != expected for row in analysed.rows)
    ):
        raise SafetyError("Returned schema does not match the explicit result-column allowlist.")
    ids = [r["record_id"] for r in analysed.rows]
    if any(not valid_id(v) for v in ids) or len(set(ids)) != len(ids):
        raise SafetyError("Returned IDs are malformed or duplicated.")
    if set(ids) != set(mapping["records"]):
        raise SafetyError("Returned IDs and mapping do not match exactly; missing or unknown IDs.")
    rows = []
    for row in analysed.rows:
        restored = {
            source_key: mapping["records"][row["record_id"]],
            **{c: row[c] for c in result_columns},
        }
        if any(formula_or_control(v) for v in restored.values()):
            raise SafetyError("Restored values contain unsafe spreadsheet formulas or controls.")
        rows.append(restored)
    return Table((source_key, *result_columns), tuple(rows))
