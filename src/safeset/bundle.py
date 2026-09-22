"""Authenticated version 2 restoration bundles for protected working copies."""

import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import InvalidToken

from .classification import formula_or_control
from .errors import SafetyError
from .ingestion import MAX_FIELD, MAX_ROWS, Table, read_bounded, valid_heading
from .mapping import MAP_LIMIT, _fernet, _unique_object
from .policy import Policy, parse_policy
from .pseudonyms import new_id, valid_id
from .storage import check_map_read

MAGIC = b"SAFESET2\n"


def source_digest(table: Table) -> str:
    """Bind the selected, normalised source table, including order and headings."""
    payload = [list(table.columns), [[row[name] for name in table.columns] for row in table.rows]]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def policy_payload(policy: Policy) -> dict:
    def number(value):
        return int(value) if value == value.to_integral_value() else float(value)

    columns = {}
    for name, rule in policy.columns.items():
        item = {"action": rule.action, "classification": rule.classification}
        if rule.action in {"keep", "code"}:
            item["allowed_values"] = list(rule.allowed_values)
        elif rule.action == "bin":
            item["bins"] = [[number(lo), number(hi)] for lo, hi in rule.bins]
        elif rule.action == "keep_numeric":
            item["bounds"] = [number(value) for value in rule.bounds]
            item["max_decimal_places"] = rule.max_decimal_places
        columns[name] = item
    return {"version": 2, "columns": columns, "min_group_size": policy.min_group_size}


def create_bundle(source: Table, policy: Policy, candidate) -> dict:
    if set(source.columns) != set(policy.columns) or candidate.mapping["version"] != 1:
        raise SafetyError("Source, policy and candidate do not match.")
    codebooks = {}
    for name, rule in policy.columns.items():
        if rule.action == "code":
            codebook = {}
            for source_row, protected_row in zip(source.rows, candidate.table.rows, strict=True):
                label, code = source_row[name], protected_row[name]
                if label in codebook and codebook[label] != code:
                    raise SafetyError("Candidate category codes are inconsistent.")
                codebook[label] = code
            codebooks[name] = codebook
    payload = policy_payload(policy)
    for name, rule in policy.columns.items():
        if rule.action in {"keep", "code"}:
            payload["columns"][name]["allowed_values"] = sorted({row[name] for row in source.rows})
    round_tripped = parse_policy(payload)
    if any(
        round_tripped.columns[name] != rule
        for name, rule in policy.columns.items()
        if rule.action not in {"keep", "code"}
    ):
        raise SafetyError("Protection policy cannot be represented in the bundle.")
    return validate_bundle(
        {
            "version": 2,
            "export_id": new_id(),
            "source_digest": source_digest(source),
            "source_column": policy.source_key,
            "source_columns": list(source.columns),
            "protected_columns": list(candidate.table.columns),
            "records": candidate.mapping["records"],
            "codebooks": codebooks,
            "policy": payload,
        }
    )


def validate_bundle(value: object) -> dict:
    keys = {
        "version",
        "export_id",
        "source_digest",
        "source_column",
        "source_columns",
        "protected_columns",
        "records",
        "codebooks",
        "policy",
    }
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or type(value["version"]) is not int
        or value["version"] != 2
    ):
        raise SafetyError("Restoration bundle version or structure is unsupported.")
    policy = parse_policy(value["policy"])
    if value["policy"]["version"] != 2:
        raise SafetyError("Restoration bundle policy version is unsupported.")
    source_columns = value["source_columns"]
    protected_columns = value["protected_columns"]
    records = value["records"]
    codebooks = value["codebooks"]
    if (
        not isinstance(source_columns, list)
        or not all(isinstance(c, str) for c in source_columns)
        or not isinstance(protected_columns, list)
        or not all(isinstance(c, str) for c in protected_columns)
    ):
        raise SafetyError("Restoration bundle schema is malformed.")
    if (
        not valid_id(value["export_id"])
        or not isinstance(value["source_digest"], str)
        or len(value["source_digest"]) != 64
        or any(c not in "0123456789abcdef" for c in value["source_digest"])
        or value["source_column"] != policy.source_key
        or not source_columns
        or len(source_columns) != len(set(source_columns))
        or any(not valid_heading(c) for c in source_columns)
        or set(source_columns) != set(policy.columns)
        or protected_columns != list(policy.output_columns)
        or not isinstance(records, dict)
        or not 1 <= len(records) <= MAX_ROWS
        or any(
            not valid_id(k)
            or not isinstance(v, str)
            or not v.strip()
            or len(v) > MAX_FIELD
            or formula_or_control(v)
            for k, v in records.items()
        )
        or len(set(records.values())) != len(records)
        or not isinstance(codebooks, dict)
        or set(codebooks) != {k for k, r in policy.columns.items() if r.action == "code"}
    ):
        raise SafetyError("Restoration bundle is malformed or ambiguous.")
    all_codes = set(records)
    for name, book in codebooks.items():
        if (
            not isinstance(book, dict)
            or not book
            or any(
                k not in policy.columns[name].allowed_values or not valid_id(v)
                for k, v in book.items()
            )
            or len(set(book.values())) != len(book)
            or not all_codes.isdisjoint(book.values())
        ):
            raise SafetyError("Restoration codebook is malformed.")
        all_codes.update(book.values())
    return value


def encrypt_bundle(bundle: dict, passphrase: str) -> bytes:
    validate_bundle(bundle)
    salt = os.urandom(16)
    payload = json.dumps(bundle, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    encrypted = MAGIC + salt + _fernet(passphrase, salt).encrypt(payload)
    if len(encrypted) > MAP_LIMIT:
        raise SafetyError("Restoration bundle exceeds the supported size limit.")
    return encrypted


def decrypt_bundle(data: bytes, passphrase: str) -> dict:
    if len(data) > MAP_LIMIT or not data.startswith(MAGIC) or len(data) < len(MAGIC) + 17:
        raise SafetyError("Restoration bundle version or envelope is unsupported.")
    salt = data[len(MAGIC) : len(MAGIC) + 16]
    try:
        payload = _fernet(passphrase, salt).decrypt(data[len(MAGIC) + 16 :])
        return validate_bundle(json.loads(payload, object_pairs_hook=_unique_object))
    except (InvalidToken, UnicodeError, ValueError, RecursionError, TypeError):
        raise SafetyError("Restoration bundle could not be authenticated or decoded.") from None


def read_bundle(path: Path, passphrase: str, *context: Path) -> dict:
    try:
        resolved = check_map_read(path, *context)
        return decrypt_bundle(read_bounded(resolved, MAP_LIMIT), passphrase)
    except OSError:
        raise SafetyError("Unable to access private restoration bundle.") from None
