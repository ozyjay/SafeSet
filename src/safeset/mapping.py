"""Versioned authenticated encrypted maps; plaintext is held only in memory."""

import base64
import json
import os
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from .errors import SafetyError
from .ingestion import MAX_FIELD, MAX_ROWS, read_bounded, valid_heading
from .pseudonyms import valid_id
from .storage import check_map_read

MAGIC = b"SAFESET1\n"
MAP_LIMIT = 32 * 1024 * 1024


def validate_mapping(mapping: object) -> dict:
    valid = (
        isinstance(mapping, dict)
        and set(mapping) == {"version", "source_column", "records"}
        and type(mapping["version"]) is int
        and mapping["version"] == 1
        and isinstance(mapping["source_column"], str)
        and valid_heading(mapping["source_column"])
        and mapping["source_column"] != "record_id"
        and isinstance(mapping["records"], dict)
        and 1 <= len(mapping["records"]) <= MAX_ROWS
    )
    if not valid:
        raise SafetyError("Mapping structure is invalid.")
    records = mapping["records"]
    if any(
        not valid_id(k) or not isinstance(v, str) or not v.strip() or len(v) > MAX_FIELD
        for k, v in records.items()
    ) or len(set(records.values())) != len(records):
        raise SafetyError("Mapping records are malformed or ambiguous.")
    return mapping


def _fernet(passphrase: str, salt: bytes) -> Fernet:
    if len(passphrase) < 16:
        raise SafetyError("Mapping passphrase must contain at least 16 characters.")
    try:
        kdf = Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=64 * 1024)
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
        return Fernet(key)
    except UnsupportedAlgorithm:
        raise SafetyError(
            "Installed cryptography backend does not support the required KDF."
        ) from None


def encrypt_mapping(mapping: dict, passphrase: str) -> bytes:
    validate_mapping(mapping)
    salt = os.urandom(16)
    payload = json.dumps(mapping, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    encrypted = MAGIC + salt + _fernet(passphrase, salt).encrypt(payload)
    if len(encrypted) > MAP_LIMIT:
        raise SafetyError("Mapping exceeds the supported size limit.")
    return encrypted


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SafetyError("Mapping contains duplicate keys.")
        result[key] = value
    return result


def decrypt_mapping(data: bytes, passphrase: str) -> dict:
    if len(data) > MAP_LIMIT or not data.startswith(MAGIC) or len(data) < len(MAGIC) + 17:
        raise SafetyError("Mapping envelope is invalid.")
    salt = data[len(MAGIC) : len(MAGIC) + 16]
    try:
        payload = _fernet(passphrase, salt).decrypt(data[len(MAGIC) + 16 :])
        return validate_mapping(json.loads(payload, object_pairs_hook=_unique_object))
    except (InvalidToken, UnicodeError, ValueError, RecursionError):
        raise SafetyError(
            "Mapping could not be authenticated or decoded; check credentials/file."
        ) from None


def read_mapping(path: Path, passphrase: str, *context: Path) -> dict:
    try:
        resolved = check_map_read(path, *context)
        return decrypt_mapping(read_bounded(resolved, MAP_LIMIT), passphrase)
    except OSError:
        raise SafetyError("Unable to access private mapping storage.") from None
