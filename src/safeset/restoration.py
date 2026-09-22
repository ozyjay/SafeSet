"""Exact local restoration of authorised result columns."""

from .classification import formula_or_control, safe_category
from .errors import SafetyError
from .ingestion import Table, valid_heading
from .mapping import validate_mapping
from .policy import Policy
from .pseudonyms import valid_id


def restore(
    analysed: Table,
    mapping: dict,
    result_columns: tuple[str, ...],
    *,
    coded_source: Table | None = None,
    coded_policy: Policy | None = None,
) -> Table:
    validate_mapping(mapping)
    if (coded_source is None) != (coded_policy is None):
        raise SafetyError("Restoring coded labels requires both the original source and policy.")
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
    coded_columns = ()
    source_by_key = {}
    if coded_source is not None and coded_policy is not None:
        if coded_policy.source_key != source_key or set(coded_source.columns) != set(
            coded_policy.columns
        ) or any(set(row) != set(coded_source.columns) for row in coded_source.rows):
            raise SafetyError("Original source, policy and identity map do not match.")
        source_keys = [row[source_key] for row in coded_source.rows]
        if (
            any(
                not isinstance(key, str) or not key.strip() or formula_or_control(key)
                for key in source_keys
            )
            or len(set(source_keys)) != len(source_keys)
            or set(source_keys) != set(mapping["records"].values())
        ):
            raise SafetyError("Original source keys do not match the identity map exactly.")
        source_by_key = dict(zip(source_keys, coded_source.rows, strict=True))
        coded_columns = tuple(
            name for name in result_columns if coded_policy.columns.get(name)
            and coded_policy.columns[name].action == "code"
        )
        if not coded_columns:
            raise SafetyError("No approved coded result columns are available to restore.")
        for name in coded_columns:
            rule = coded_policy.columns[name]
            category_to_code = {}
            code_to_category = {}
            for row in analysed.rows:
                category = source_by_key[mapping["records"][row["record_id"]]][name]
                code = row[name]
                if (
                    category not in rule.allowed_values
                    or not safe_category(category)
                    or not valid_id(code)
                    or category_to_code.get(category, code) != code
                    or code_to_category.get(code, category) != category
                ):
                    raise SafetyError("Coded results do not match the original source categories.")
                category_to_code[category] = code
                code_to_category[code] = category
    rows = []
    for row in analysed.rows:
        restored = {
            source_key: mapping["records"][row["record_id"]],
            **{c: row[c] for c in result_columns},
        }
        if coded_columns:
            source_row = source_by_key[restored[source_key]]
            for name in coded_columns:
                restored[name] = source_row[name]
        if any(formula_or_control(v) for v in restored.values()):
            raise SafetyError("Restored values contain unsafe spreadsheet formulas or controls.")
        rows.append(restored)
    return Table((source_key, *result_columns), tuple(rows))
