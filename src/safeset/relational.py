"""Fail-closed multi-sheet protection with explicit cross-sheet entity linkage."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from cryptography.fernet import InvalidToken

from .bundle import policy_payload, source_digest
from .classification import canonical_numeric, formula_or_control, safe_category
from .errors import SafetyError
from .ingestion import (
    MAX_BYTES,
    MAX_COLUMNS,
    MAX_FIELD,
    MAX_ROWS,
    Table,
    excel_workbook_bytes,
    read_bounded,
    read_excel_sheets,
    require_excel_path,
    valid_heading,
)
from .mapping import MAP_LIMIT, _fernet, _unique_object
from .policy import Policy, parse_policy
from .pseudonyms import new_id, valid_id
from .storage import check_map_read, map_destination, output_destination, private_directory, publish
from .validation import ValidationReport, validate

MAGIC = b"SAFESET3\n"
PROFILES = {"strict", "controlled_pseudonymisation"}


@dataclass(frozen=True)
class RelationalCandidate:
    tables: dict[str, Table]
    records: dict[str, dict[str, dict[str, object]]]
    entities: dict[str, str]
    codebooks: dict[str, dict[str, dict[str, str]]]
    shared_code_fields: tuple[str, ...]


@dataclass(frozen=True)
class RelationalValidation:
    profile: str
    sheets: dict[str, ValidationReport]
    minimum_linked_group_size: int
    linked_unique_entities: int
    linked_small_entities: int
    linked_errors: tuple[str, ...]
    linked_warnings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.linked_errors and all(report.passed for report in self.sheets.values())

    def require_pass(self) -> None:
        if not self.passed:
            raise SafetyError("Validation failed; no export is permitted.")

    def summary(self) -> dict:
        warnings = [
            f"Worksheet {name}: {warning}"
            for name, report in self.sheets.items()
            for warning in report.warnings
        ]
        warnings.extend(self.linked_warnings)
        errors = [
            f"Worksheet {name}: {error}"
            for name, report in self.sheets.items()
            for error in report.errors
        ]
        errors.extend(self.linked_errors)
        return {
            "profile": self.profile,
            "passed": self.passed,
            "warnings": warnings,
            "errors": errors,
            "sheets": {name: report.summary() for name, report in self.sheets.items()},
            "minimum_linked_group_size": self.minimum_linked_group_size,
            "linked_unique_entities": self.linked_unique_entities,
            "linked_small_entities": self.linked_small_entities,
            "linked_errors": list(self.linked_errors),
            "linked_warnings": list(self.linked_warnings),
            "notice": (
                "Shared entity IDs deliberately expose cross-sheet linkability. "
                "Passing checks does not establish anonymity."
            ),
        }


def workbook_digest(tables: dict[str, Table]) -> str:
    payload = [[name, source_digest(table)] for name, table in tables.items()]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _new_unique(issued: set[str], message: str) -> str:
    value = new_id()
    if value in issued:
        raise SafetyError(message)
    issued.add(value)
    return value


def _transform_value(value: str, rule, codes: dict[str, str], issued: set[str]) -> str:
    if rule.action == "keep":
        if value not in rule.allowed_values:
            raise SafetyError("Source category is outside the approved domain.")
        return value
    if rule.action == "code":
        if value not in rule.allowed_values:
            raise SafetyError("Source category is outside the approved domain.")
        if value not in codes:
            codes[value] = _new_unique(issued, "Random code collision; no export produced.")
        return codes[value]
    if rule.action == "keep_numeric":
        result = canonical_numeric(value, rule.bounds, rule.max_decimal_places)
        if result is None:
            raise SafetyError("Numeric input violates approved bounds or format.")
        return result
    if rule.action == "bin":
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise SafetyError("A numeric input cannot be binned.") from None
        if not number.is_finite():
            raise SafetyError("Non-finite numeric input is prohibited.")
        for index, (low, high) in enumerate(rule.bins):
            if low <= number < high or (index == len(rule.bins) - 1 and number == high):
                return rule.labels[index]
        raise SafetyError("Numeric input falls outside approved bins.")
    raise SafetyError("Unsupported relational transformation.")


def _validated_shared_code_fields(
    policies: dict[str, Policy], shared_code_fields: tuple[str, ...]
) -> tuple[str, ...]:
    if (
        any(not isinstance(name, str) or not valid_heading(name) for name in shared_code_fields)
        or len(shared_code_fields) != len(set(shared_code_fields))
        or any(
            sum(
                name in policy.columns and policy.columns[name].action == "code"
                for policy in policies.values()
            )
            < 2
            for name in shared_code_fields
        )
    ):
        raise SafetyError(
            "Every shared obfuscation field must be coded in at least two selected worksheets."
        )
    return shared_code_fields


def sanitise_relational(
    sources: dict[str, Table],
    policies: dict[str, Policy],
    shared_code_fields: tuple[str, ...] = (),
) -> RelationalCandidate:
    if not sources or set(sources) != set(policies):
        raise SafetyError("Every selected worksheet needs an explicit policy.")
    if sum(len(table.rows) for table in sources.values()) > MAX_ROWS:
        raise SafetyError("Selected worksheets exceed the combined row limit.")
    shared_code_fields = _validated_shared_code_fields(policies, shared_code_fields)
    issued: set[str] = set()
    source_to_entity: dict[str, str] = {}
    entities: dict[str, str] = {}
    tables: dict[str, Table] = {}
    records: dict[str, dict[str, dict[str, object]]] = {}
    codebooks: dict[str, dict[str, dict[str, str]]] = {}
    shared_books: dict[str, dict[str, str]] = {name: {} for name in shared_code_fields}
    for sheet, source in sources.items():
        policy = policies[sheet]
        if set(source.columns) != set(policy.columns):
            raise SafetyError("Source schema differs from policy; missing or unexpected columns.")
        if not source.rows:
            raise SafetyError("Empty worksheets cannot be exported.")
        if "record_id" in source.columns or "entity_id" in source.columns:
            raise SafetyError("Source worksheets use a reserved relational heading.")
        sheet_rows = []
        sheet_records: dict[str, dict[str, object]] = {}
        sheet_books: dict[str, dict[str, str]] = {
            name: {} for name, rule in policy.columns.items() if rule.action == "code"
        }
        for row_index, row in enumerate(source.rows):
            source_key = row[policy.source_key]
            if not source_key.strip() or formula_or_control(source_key):
                raise SafetyError("Source keys must be non-empty and safe text.")
            if source_key not in source_to_entity:
                entity_id = _new_unique(issued, "Random ID collision; no export produced.")
                source_to_entity[source_key] = entity_id
                entities[entity_id] = source_key
            entity_id = source_to_entity[source_key]
            record_id = _new_unique(issued, "Random ID collision; no export produced.")
            result = {"record_id": record_id, "entity_id": entity_id}
            for name, rule in policy.columns.items():
                if rule.action in {"keep", "code", "keep_numeric", "bin"}:
                    codes = (
                        shared_books[name]
                        if rule.action == "code" and name in shared_books
                        else sheet_books[name]
                        if rule.action == "code"
                        else {}
                    )
                    result[name] = _transform_value(row[name], rule, codes, issued)
                    if rule.action == "code":
                        sheet_books[name][row[name]] = codes[row[name]]
            sheet_rows.append(result)
            sheet_records[record_id] = {"row": row_index, "entity_id": entity_id}
        columns = ("record_id", "entity_id", *policy.output_columns[1:])
        tables[sheet] = Table(columns, tuple(sheet_rows))
        records[sheet] = sheet_records
        codebooks[sheet] = sheet_books
    return RelationalCandidate(tables, records, entities, codebooks, shared_code_fields)


def validate_relational(
    candidate: RelationalCandidate,
    policies: dict[str, Policy],
    profile: str = "strict",
) -> RelationalValidation:
    if not isinstance(profile, str) or profile not in PROFILES:
        raise SafetyError("Validation profile is unsupported.")
    if set(candidate.tables) != set(policies):
        raise SafetyError("Relational candidate and policies do not match.")
    _validated_shared_code_fields(policies, candidate.shared_code_fields)
    reports = {}
    entity_features: dict[str, list[tuple[str, str, str]]] = {
        entity_id: [] for entity_id in candidate.entities
    }
    all_records: set[str] = set()
    for sheet, table in candidate.tables.items():
        policy = policies[sheet]
        expected = ("record_id", "entity_id", *policy.output_columns[1:])
        if table.columns != expected or any(set(row) != set(expected) for row in table.rows):
            raise SafetyError("Relational protected schema is malformed.")
        projected = Table(
            policy.output_columns,
            tuple({name: row[name] for name in policy.output_columns} for row in table.rows),
        )
        reports[sheet] = validate(projected, policy, profile)
        for row in table.rows:
            record_id = row["record_id"]
            entity_id = row["entity_id"]
            if (
                not valid_id(record_id)
                or record_id in all_records
                or not valid_id(entity_id)
                or entity_id not in candidate.entities
            ):
                raise SafetyError("Relational identifiers are malformed or ambiguous.")
            all_records.add(record_id)
            for name in policy.output_columns[1:]:
                entity_features[entity_id].append((sheet, name, row[name]))
    fingerprints = Counter(tuple(sorted(features)) for features in entity_features.values())
    minimum = min(fingerprints.values()) if fingerprints else 0
    unique = sum(size == 1 for size in fingerprints.values())
    threshold = max(policy.min_group_size for policy in policies.values())
    small = sum(size for size in fingerprints.values() if size < threshold)
    errors: list[str] = []
    warnings: list[str] = [
        "Shared entity IDs expose equality and participation patterns across worksheets."
    ]
    if candidate.shared_code_fields:
        warnings.append(
            "Shared obfuscation codebooks expose cross-worksheet category equality and frequency."
        )
    if small:
        finding = "Small linked equivalence classes fall below the release threshold."
        if profile == "strict":
            errors.append(finding)
        else:
            warnings.append(f"Controlled pseudonymisation risk accepted for review: {finding}")
    return RelationalValidation(
        profile, reports, minimum, unique, small, tuple(errors), tuple(warnings)
    )


def _bundle_sheet(
    source: Table, policy: Policy, candidate: RelationalCandidate, sheet: str
) -> dict:
    payload = policy_payload(policy)
    for name, rule in policy.columns.items():
        if rule.action in {"keep", "code"}:
            payload["columns"][name]["allowed_values"] = sorted({row[name] for row in source.rows})
    parse_policy(payload)
    return {
        "source_digest": source_digest(source),
        "source_column": policy.source_key,
        "source_columns": list(source.columns),
        "protected_columns": list(candidate.tables[sheet].columns),
        "records": candidate.records[sheet],
        "codebooks": candidate.codebooks[sheet],
        "policy": payload,
    }


def create_relational_bundle(
    sources: dict[str, Table],
    policies: dict[str, Policy],
    candidate: RelationalCandidate,
    profile: str,
) -> dict:
    if (
        not isinstance(profile, str)
        or profile not in PROFILES
        or set(sources) != set(policies)
        or set(sources) != set(candidate.tables)
    ):
        raise SafetyError("Relational protection inputs do not match.")
    return validate_relational_bundle(
        {
            "version": 3,
            "export_id": new_id(),
            "profile": profile,
            "workbook_digest": workbook_digest(sources),
            "entities": candidate.entities,
            "shared_code_fields": list(candidate.shared_code_fields),
            "sheets": {
                name: _bundle_sheet(sources[name], policies[name], candidate, name)
                for name in sources
            },
        }
    )


def validate_relational_bundle(value: object) -> dict:
    legacy_keys = {"version", "export_id", "profile", "workbook_digest", "entities", "sheets"}
    keys = legacy_keys | {"shared_code_fields"}
    if isinstance(value, dict) and set(value) == legacy_keys:
        value = {**value, "shared_code_fields": []}
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or type(value["version"]) is not int
        or value["version"] != 3
        or not valid_id(value["export_id"])
        or not isinstance(value["profile"], str)
        or value["profile"] not in PROFILES
        or not isinstance(value["workbook_digest"], str)
        or len(value["workbook_digest"]) != 64
        or any(character not in "0123456789abcdef" for character in value["workbook_digest"])
        or not isinstance(value["entities"], dict)
        or not isinstance(value["shared_code_fields"], list)
        or any(
            not isinstance(name, str) or not valid_heading(name)
            for name in value["shared_code_fields"]
        )
        or len(value["shared_code_fields"]) != len(set(value["shared_code_fields"]))
        or not isinstance(value["sheets"], dict)
        or not value["sheets"]
    ):
        raise SafetyError("Relational restoration bundle version or structure is unsupported.")
    entities = value["entities"]
    if (
        not entities
        or len(entities) > MAX_ROWS
        or any(
            not valid_id(entity_id)
            or not isinstance(source_key, str)
            or not source_key.strip()
            or len(source_key) > MAX_FIELD
            or formula_or_control(source_key)
            for entity_id, source_key in entities.items()
        )
        or len(set(entities.values())) != len(entities)
    ):
        raise SafetyError("Relational entity map is malformed or ambiguous.")
    shared_code_fields = tuple(value["shared_code_fields"])
    policies = {}
    declared_record_ids = []
    for sheet, item in value["sheets"].items():
        item_keys = {
            "source_digest",
            "source_column",
            "source_columns",
            "protected_columns",
            "records",
            "codebooks",
            "policy",
        }
        if not valid_heading(sheet) or not isinstance(item, dict) or set(item) != item_keys:
            raise SafetyError("Relational worksheet bundle is malformed.")
        policies[sheet] = parse_policy(item["policy"])
        if not isinstance(item["records"], dict):
            raise SafetyError("Relational row mapping is malformed or ambiguous.")
        declared_record_ids.extend(item["records"])
    _validated_shared_code_fields(policies, shared_code_fields)
    if len(declared_record_ids) != len(set(declared_record_ids)) or any(
        not valid_id(record_id) for record_id in declared_record_ids
    ):
        raise SafetyError("Relational row mapping is malformed or ambiguous.")
    seen_records: set[str] = set()
    all_codes = set(entities) | set(declared_record_ids)
    shared_assignments: dict[tuple[str, str], str] = {}
    total_rows = 0
    for sheet, item in value["sheets"].items():
        item_keys = {
            "source_digest",
            "source_column",
            "source_columns",
            "protected_columns",
            "records",
            "codebooks",
            "policy",
        }
        policy = policies[sheet]
        source_columns = item["source_columns"]
        protected_columns = item["protected_columns"]
        records = item["records"]
        books = item["codebooks"]
        if (
            item["source_column"] != policy.source_key
            or not isinstance(item["source_digest"], str)
            or len(item["source_digest"]) != 64
            or any(character not in "0123456789abcdef" for character in item["source_digest"])
            or not isinstance(source_columns, list)
            or set(source_columns) != set(policy.columns)
            or len(source_columns) != len(set(source_columns))
            or any(not valid_heading(name) for name in source_columns)
            or protected_columns != ["record_id", "entity_id", *policy.output_columns[1:]]
            or len(protected_columns) > MAX_COLUMNS
            or not isinstance(records, dict)
            or not records
            or not isinstance(books, dict)
            or set(books)
            != {name for name, rule in policy.columns.items() if rule.action == "code"}
        ):
            raise SafetyError("Relational worksheet bundle is malformed.")
        row_indexes = set()
        for record_id, record in records.items():
            if (
                not valid_id(record_id)
                or record_id in seen_records
                or not isinstance(record, dict)
                or set(record) != {"row", "entity_id"}
                or type(record["row"]) is not int
                or record["row"] < 0
                or record["row"] in row_indexes
                or record["entity_id"] not in entities
            ):
                raise SafetyError("Relational row mapping is malformed or ambiguous.")
            seen_records.add(record_id)
            row_indexes.add(record["row"])
        if row_indexes != set(range(len(records))):
            raise SafetyError("Relational row mapping coverage is incomplete.")
        total_rows += len(records)
        for name, book in books.items():
            if (
                not isinstance(book, dict)
                or not book
                or any(
                    label not in policy.columns[name].allowed_values or not valid_id(code)
                    for label, code in book.items()
                )
                or len(set(book.values())) != len(book)
            ):
                raise SafetyError("Relational category codebook is malformed.")
            for label, code in book.items():
                shared_key = (name, label)
                previous = (
                    shared_assignments.get(shared_key) if name in shared_code_fields else None
                )
                if previous is not None:
                    if previous != code:
                        raise SafetyError("Relational shared category codebook is inconsistent.")
                    continue
                if code in all_codes:
                    raise SafetyError("Relational category codebook is malformed.")
                all_codes.add(code)
                if name in shared_code_fields:
                    shared_assignments[shared_key] = code
    if total_rows > MAX_ROWS:
        raise SafetyError("Relational restoration bundle exceeds the row limit.")
    return value


def encrypt_relational_bundle(bundle: dict, passphrase: str) -> bytes:
    validate_relational_bundle(bundle)
    salt = os.urandom(16)
    payload = json.dumps(bundle, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    result = MAGIC + salt + _fernet(passphrase, salt).encrypt(payload)
    if len(result) > MAP_LIMIT:
        raise SafetyError("Relational restoration bundle exceeds the supported size limit.")
    return result


def decrypt_relational_bundle(data: bytes, passphrase: str) -> dict:
    if len(data) > MAP_LIMIT or not data.startswith(MAGIC) or len(data) < len(MAGIC) + 17:
        raise SafetyError("Relational restoration bundle envelope is unsupported.")
    salt = data[len(MAGIC) : len(MAGIC) + 16]
    try:
        payload = _fernet(passphrase, salt).decrypt(data[len(MAGIC) + 16 :])
        return validate_relational_bundle(json.loads(payload, object_pairs_hook=_unique_object))
    except (InvalidToken, UnicodeError, ValueError, RecursionError, TypeError):
        raise SafetyError(
            "Relational restoration bundle could not be authenticated or decoded."
        ) from None


def read_relational_bundle(path: Path, passphrase: str, *context: Path) -> dict:
    try:
        resolved = check_map_read(path, *context)
        return decrypt_relational_bundle(read_bounded(resolved, MAP_LIMIT), passphrase)
    except OSError:
        raise SafetyError("Unable to access private relational restoration bundle.") from None


def protect_relational(
    source_path: Path,
    sheets: tuple[str, ...],
    policies: dict[str, Policy],
    output: Path,
    bundle_path: Path,
    passphrase: str,
    *,
    profile: str,
    approved: bool,
    shared_code_fields: tuple[str, ...] = (),
) -> RelationalValidation:
    if not approved:
        raise SafetyError("Explicit relational protection approval is required.")
    sources = read_excel_sheets(
        source_path, sheets, allow_cached_formulas=True, allow_source_dates=True
    )
    candidate = sanitise_relational(sources, policies, shared_code_fields)
    validation = validate_relational(candidate, policies, profile)
    validation.require_pass()
    publish_relational_candidate(
        source_path,
        sheets,
        sources,
        policies,
        candidate,
        validation,
        output,
        bundle_path,
        passphrase,
        approved=True,
    )
    return validation


def publish_relational_candidate(
    source_path: Path,
    sheets: tuple[str, ...],
    sources: dict[str, Table],
    policies: dict[str, Policy],
    candidate: RelationalCandidate,
    validation: RelationalValidation,
    output: Path,
    bundle_path: Path,
    passphrase: str,
    *,
    approved: bool,
) -> None:
    """Recheck a reviewed workbook set and publish its bundle before its workbook."""
    if not approved:
        raise SafetyError("Explicit relational protection approval is required.")
    validation.require_pass()
    current = read_excel_sheets(
        source_path, sheets, allow_cached_formulas=True, allow_source_dates=True
    )
    if workbook_digest(current) != workbook_digest(sources):
        raise SafetyError("Source workbook changed after relational protection review.")
    fresh_validation = validate_relational(candidate, policies, validation.profile)
    fresh_validation.require_pass()
    bundle = create_relational_bundle(sources, policies, candidate, validation.profile)
    require_excel_path(output)
    destination = output_destination(output, source_path)
    private_bundle = map_destination(bundle_path, destination, source_path)
    workbook = excel_workbook_bytes(candidate.tables)
    if len(workbook) > MAX_BYTES:
        raise SafetyError("Protected workbook exceeds the supported size limit.")
    encrypted = encrypt_relational_bundle(bundle, passphrase)
    private_directory(private_bundle.parent, create=True)
    publish(private_bundle, encrypted)
    try:
        publish(destination, workbook)
    except SafetyError:
        raise SafetyError("Protection publication failed; a private bundle was retained.") from None


def _expected(value: str, name: str, rule, codebooks: dict[str, dict[str, str]]) -> str:
    if rule.action == "keep":
        if value not in rule.allowed_values:
            raise SafetyError("Original source violates the bound protection policy.")
        return value
    if rule.action == "code":
        try:
            return codebooks[name][value]
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


def review_relational_reconstruction(
    sources: dict[str, Table], returned: dict[str, Table], bundle: dict
) -> dict[str, tuple[str, ...]]:
    validate_relational_bundle(bundle)
    if set(sources) != set(bundle["sheets"]) or set(returned) != set(bundle["sheets"]):
        raise SafetyError("Relational workbook worksheet coverage does not match the bundle.")
    if workbook_digest(sources) != bundle["workbook_digest"]:
        raise SafetyError("Original workbook does not match the relational restoration bundle.")
    result: dict[str, tuple[str, ...]] = {}
    seen_records: set[str] = set()
    entities = bundle["entities"]
    for sheet, item in bundle["sheets"].items():
        source = sources[sheet]
        table = returned[sheet]
        policy = parse_policy(item["policy"])
        protected = tuple(item["protected_columns"])
        if source.columns != tuple(item["source_columns"]):
            raise SafetyError("Original worksheet schema does not match the bundle.")
        if table.columns[: len(protected)] != protected:
            raise SafetyError("Protected worksheet schema has changed unexpectedly.")
        new_columns = table.columns[len(protected) :]
        if (
            len(table.columns) > MAX_COLUMNS
            or len(set(table.columns)) != len(table.columns)
            or any(not valid_heading(name) or name in source.columns for name in new_columns)
            or any(set(row) != set(table.columns) for row in table.rows)
        ):
            raise SafetyError("Returned relational workbook contains unexpected fields.")
        records = item["records"]
        ids = [row["record_id"] for row in table.rows]
        if set(ids) != set(records) or len(ids) != len(set(ids)) or seen_records.intersection(ids):
            raise SafetyError("Returned relational record coverage does not match the bundle.")
        seen_records.update(ids)
        for row in table.rows:
            record = records[row["record_id"]]
            original = source.rows[record["row"]]
            entity_id = record["entity_id"]
            if row["entity_id"] != entity_id or original[policy.source_key] != entities[entity_id]:
                raise SafetyError("Returned relational entity linkage has changed.")
            for name in policy.output_columns[1:]:
                if row[name] != _expected(
                    original[name], name, policy.columns[name], item["codebooks"]
                ):
                    raise SafetyError("A protected source field was changed.")
            if any(
                not safe_category(row[name]) or len(row[name]) > MAX_FIELD for name in new_columns
            ):
                raise SafetyError("New result contains unsafe or unsupported spreadsheet text.")
        if any(formula_or_control(value) for row in source.rows for value in row.values()):
            raise SafetyError("Original source contains unsafe spreadsheet text.")
        result[sheet] = new_columns
    return result


def reconstruct_relational(
    sources: dict[str, Table],
    returned: dict[str, Table],
    bundle: dict,
    approved_results: dict[str, tuple[str, ...]],
) -> dict[str, Table]:
    available = review_relational_reconstruction(sources, returned, bundle)
    if set(approved_results) != set(available) or any(
        len(set(approved_results[sheet])) != len(approved_results[sheet])
        or set(approved_results[sheet]) != set(columns)
        for sheet, columns in available.items()
    ):
        raise SafetyError("Every new relational result field requires explicit approval.")
    result = {}
    for sheet, item in bundle["sheets"].items():
        source = sources[sheet]
        rows = []
        for row in returned[sheet].rows:
            original = source.rows[item["records"][row["record_id"]]["row"]]
            rows.append(
                {
                    **original,
                    **{name: row[name] for name in approved_results[sheet]},
                }
            )
        result[sheet] = Table((*source.columns, *approved_results[sheet]), tuple(rows))
    return result
