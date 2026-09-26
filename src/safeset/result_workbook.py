"""Result-only workbook restoration with explicit local source-field joins."""

import copy
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from .classification import has_control, safe_category
from .errors import SafetyError
from .ingestion import (
    MAX_BYTES,
    MAX_COLUMNS,
    Table,
    excel_workbook_bytes,
    list_excel_sheets,
    read_excel_sheets,
    require_excel_path,
)
from .policy import parse_policy
from .pseudonyms import valid_id
from .relational import read_relational_bundle, workbook_digest
from .storage import output_destination, publish
from .workbook_editing import file_digest

RESULT_ERROR = "Result workbook structure, identities or values are invalid."
JOIN_ERROR = "Result source-field selections or identity joins are invalid."
APPROVAL_ERROR = "Review every result sheet, field and new category before restoration."
STALE_ERROR = "A workbook changed after result-workbook review."


@dataclass(frozen=True)
class ResultWorkbookReview:
    returned_path: Path
    source_path: Path
    bundle_path: Path
    output: Path
    bundle: dict
    returned_digest: str
    source_digest: str
    joins: dict
    summary: dict
    proposal_digest: str | None
    workbook_bytes: bytes | None


def prepare_result_workbook(returned, source, bundle_path, output, passphrase):
    bundle = read_relational_bundle(bundle_path, passphrase, returned, source, output)
    return _prepare(returned, source, bundle_path, output, bundle, {})


def update_result_workbook(review, joins):
    _unchanged(review)
    return _prepare(
        review.returned_path,
        review.source_path,
        review.bundle_path,
        review.output,
        review.bundle,
        joins,
    )


def _unchanged(review):
    if (
        file_digest(review.returned_path) != review.returned_digest
        or file_digest(review.source_path) != review.source_digest
    ):
        raise SafetyError(STALE_ERROR)


def _sources(source, bundle):
    if bundle["version"] == 5:
        raise SafetyError("Result-workbook joins do not support confirmed-region bundles.")
    tables = read_excel_sheets(
        source, tuple(bundle["sheets"]), allow_cached_formulas=True, allow_source_dates=True
    )
    if workbook_digest(tables) != bundle["workbook_digest"] or (
        bundle["version"] == 4 and file_digest(source) != bundle["source_file_digest"]
    ):
        raise SafetyError("Original workbook does not match the relational restoration bundle.")
    return tables


def _domains(bundle):
    """Return authenticated code and observed-value domains by exact field heading."""
    codes = {}
    known = {}
    coded_sheets = {}
    for sheet, item in bundle["sheets"].items():
        policy = parse_policy(item["policy"])
        for field, rule in policy.columns.items():
            if rule.action == "keep":
                known.setdefault(field, set()).update(rule.allowed_values)
        for field, book in item["codebooks"].items():
            coded_sheets.setdefault(field, set()).add(sheet)
            reverse = codes.setdefault(field, {})
            known.setdefault(field, set()).update(book)
            for label, code in book.items():
                if code in reverse and reverse[code] != label:
                    raise SafetyError(RESULT_ERROR)
                reverse[code] = label
    ambiguous = {
        field
        for field, sheets in coded_sheets.items()
        if len(sheets) > 1 and field not in bundle["shared_code_fields"]
    }
    return codes, known, ambiguous


def _result_value(value, field, codes, known, ambiguous):
    if value == "":
        return "", False
    if not safe_category(value):
        raise SafetyError(RESULT_ERROR)
    book = codes.get(field, {})
    if value in book:
        if field in ambiguous:
            raise SafetyError(RESULT_ERROR)
        return book[value], False
    try:
        uuid_shaped = str(UUID(value)) == value.lower()
    except (ValueError, AttributeError, TypeError):
        uuid_shaped = False
    if uuid_shaped:
        raise SafetyError(RESULT_ERROR)
    return value, value not in known.get(field, set())


def _joins(joins, returned, bundle):
    if not isinstance(joins, dict) or set(joins) - set(returned):
        raise SafetyError(JOIN_ERROR)
    for name, config in joins.items():
        if (
            "entity_id" not in returned[name].columns
            or not isinstance(config, dict)
            or set(config) != {"source_sheet", "source_fields", "join_by", "unique_entities"}
            or not isinstance(config["source_sheet"], str)
            or config["source_sheet"] not in bundle["sheets"]
            or not isinstance(config["source_fields"], list)
            or not config["source_fields"]
            or any(not isinstance(field, str) for field in config["source_fields"])
            or len(config["source_fields"]) != len(set(config["source_fields"]))
            or not isinstance(config["join_by"], str)
            or config["join_by"] not in {"entity_id", "record_id"}
            or type(config["unique_entities"]) is not bool
        ):
            raise SafetyError(JOIN_ERROR)
        if config["join_by"] == "record_id" and "record_id" not in returned[name].columns:
            raise SafetyError(JOIN_ERROR)
        source_columns = set(bundle["sheets"][config["source_sheet"]]["source_columns"])
        result_columns = set(returned[name].columns) - {"entity_id", "record_id"}
        if (
            set(config["source_fields"]) - source_columns
            or set(config["source_fields"]) & result_columns
        ):
            raise SafetyError(JOIN_ERROR)


def _source_index(source, item, join_by):
    index = {}
    for record_id, record in item["records"].items():
        key = record["entity_id"] if join_by == "entity_id" else record_id
        if key in index:
            raise SafetyError(JOIN_ERROR)
        index[key] = source.rows[record["row"]]
    return index


def _prepare(returned_path, source_path, bundle_path, output, bundle, joins):
    joins = copy.deepcopy(joins)
    require_excel_path(output)
    destination = output_destination(output, returned_path, source_path, bundle_path)
    source_digest = file_digest(source_path)
    returned_digest = file_digest(returned_path)
    sources = _sources(source_path, bundle)
    names = list_excel_sheets(returned_path, reject_hidden=True)
    returned = read_excel_sheets(returned_path, names)
    _joins(joins, returned, bundle)
    records = {
        record_id: (sheet, record["entity_id"])
        for sheet, item in bundle["sheets"].items()
        for record_id, record in item["records"].items()
    }
    codes, known, ambiguous = _domains(bundle)
    summary_sheets = {}
    restored = {}
    for name, table in returned.items():
        linked = "entity_id" in table.columns
        if "record_id" in table.columns and not linked:
            raise SafetyError(RESULT_ERROR)
        fields = tuple(field for field in table.columns if field not in {"entity_id", "record_id"})
        if not fields:
            raise SafetyError(RESULT_ERROR)
        seen_entities = set()
        blank_record_ids = 0
        new_values = {field: set() for field in fields}
        decoded_rows = []
        for row in table.rows:
            if linked:
                entity = row["entity_id"]
                if not valid_id(entity) or entity not in bundle["entities"]:
                    raise SafetyError(RESULT_ERROR)
                record_id = row.get("record_id")
                if record_id == "":
                    blank_record_ids += 1
                elif record_id is not None and (
                    record_id not in records or records[record_id][1] != entity
                ):
                    raise SafetyError(RESULT_ERROR)
                if name in joins and joins[name]["unique_entities"]:
                    if entity in seen_entities:
                        raise SafetyError(RESULT_ERROR)
                    seen_entities.add(entity)
            decoded = {}
            for field in fields:
                decoded[field], novel = _result_value(
                    row[field], field, codes, known, ambiguous
                )
                if novel:
                    new_values[field].add(decoded[field])
            decoded_rows.append(decoded)
        summary_sheets[name] = {
            "rows": len(table.rows),
            "linked": linked,
            "has_record_id": "record_id" in table.columns,
            "blank_record_ids": blank_record_ids,
            "result_fields": list(fields),
            "new_categories": {
                field: len(values) for field, values in new_values.items() if values
            },
        }
        if not linked:
            restored[name] = Table(fields, tuple(decoded_rows))
            continue
        if name not in joins:
            continue
        config = joins[name]
        source_sheet = config["source_sheet"]
        selected = tuple(config["source_fields"])
        columns = (*selected, *fields)
        if len(columns) > MAX_COLUMNS:
            raise SafetyError(JOIN_ERROR)
        index = _source_index(
            sources[source_sheet], bundle["sheets"][source_sheet], config["join_by"]
        )
        joined_rows = []
        for row, decoded in zip(table.rows, decoded_rows, strict=True):
            if config["join_by"] == "record_id":
                record_id = row["record_id"]
                if not record_id or records[record_id][0] != source_sheet:
                    raise SafetyError(JOIN_ERROR)
                key = record_id
            else:
                key = row["entity_id"]
            original = index.get(key)
            if original is None or any(has_control(original[field]) for field in selected):
                raise SafetyError(JOIN_ERROR)
            joined_rows.append({**{field: original[field] for field in selected}, **decoded})
        restored[name] = Table(columns, tuple(joined_rows))
    ready = all(not info["linked"] or name in joins for name, info in summary_sheets.items())
    proposal_digest = workbook_digest(restored) if ready else None
    encoded = excel_workbook_bytes(restored) if ready else None
    if encoded is not None and len(encoded) > MAX_BYTES:
        raise SafetyError("Restored workbook exceeds the supported size limit.")
    review = ResultWorkbookReview(
        returned_path,
        source_path,
        bundle_path,
        destination,
        bundle,
        returned_digest,
        source_digest,
        joins,
        {
            "result_workbook": True,
            "ready": ready,
            "sheets": summary_sheets,
            "source_columns": {
                name: item["source_columns"] for name, item in bundle["sheets"].items()
            },
            "output": str(destination),
        },
        proposal_digest,
        encoded,
    )
    _unchanged(review)
    return review


def approve_result_workbook(
    review, approved_fields, approved_categories, approved_joins, *, authorised
):
    sheets = review.summary["sheets"]
    expected_fields = {name: set(info["result_fields"]) for name, info in sheets.items()}
    expected_categories = {name: set(info["new_categories"]) for name, info in sheets.items()}
    expected_joins = {name for name, info in sheets.items() if info["linked"]}
    if (
        authorised is not True
        or not review.summary["ready"]
        or review.workbook_bytes is None
        or not isinstance(approved_fields, dict)
        or not isinstance(approved_categories, dict)
        or not isinstance(approved_joins, (list, tuple))
        or any(not isinstance(name, str) for name in approved_joins)
        or len(approved_joins) != len(set(approved_joins))
        or set(approved_joins) != expected_joins
        or set(approved_fields) != set(sheets)
        or set(approved_categories) != set(sheets)
        or any(
            not isinstance(approved_fields[name], (list, tuple))
            or any(not isinstance(field, str) for field in approved_fields[name])
            or len(approved_fields[name]) != len(set(approved_fields[name]))
            or set(approved_fields[name]) != expected_fields[name]
            or not isinstance(approved_categories[name], (list, tuple))
            or any(not isinstance(field, str) for field in approved_categories[name])
            or len(approved_categories[name]) != len(set(approved_categories[name]))
            or set(approved_categories[name]) != expected_categories[name]
            for name in sheets
        )
    ):
        raise SafetyError(APPROVAL_ERROR)
    _unchanged(review)
    fresh = _prepare(
        review.returned_path,
        review.source_path,
        review.bundle_path,
        review.output,
        review.bundle,
        review.joins,
    )
    if fresh.proposal_digest != review.proposal_digest:
        raise SafetyError(STALE_ERROR)
    publish(review.output, fresh.workbook_bytes)
    return sum(info["rows"] for info in sheets.values())
