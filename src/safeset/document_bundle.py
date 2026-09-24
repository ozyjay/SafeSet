"""Authenticated private bundles for protected DOCX documents."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import InvalidToken

from .document import MAX_DOCUMENT_TERM
from .errors import SafetyError
from .ingestion import read_bounded
from .mapping import MAP_LIMIT, _fernet, _unique_object
from .storage import check_map_read

MAGIC = b"SAFESETD1\n"
MAX_REPLACEMENTS = 128


def validate_document_bundle(value: object) -> dict:
    keys = {
        "version",
        "document_id",
        "source_digest",
        "protected_digest",
        "replacements",
        "comments_removed",
    }
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or type(value["version"]) is not int
        or value["version"] != 1
        or not isinstance(value["document_id"], str)
        or len(value["document_id"]) != 36
        or not isinstance(value["source_digest"], str)
        or len(value["source_digest"]) != 64
        or not isinstance(value["protected_digest"], str)
        or len(value["protected_digest"]) != 64
        or type(value["comments_removed"]) is not bool
        or not isinstance(value["replacements"], list)
        or len(value["replacements"]) > MAX_REPLACEMENTS
    ):
        raise SafetyError("Document restoration bundle version or structure is unsupported.")
    if any(ch not in "0123456789abcdef" for ch in value["source_digest"] + value["protected_digest"]):
        raise SafetyError("Document restoration bundle is malformed.")

    tokens = set()
    originals = set()
    for item in value["replacements"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"token", "original", "kind", "count"}
            or not isinstance(item["token"], str)
            or not item["token"].startswith("[SAFESET-")
            or not item["token"].endswith("]")
            or len(item["token"]) > 64
            or not isinstance(item["original"], str)
            or not 3 <= len(item["original"]) <= MAX_DOCUMENT_TERM
            or item["kind"] not in {"person", "email", "identifier", "other"}
            or type(item["count"]) is not int
            or item["count"] < 1
            or item["token"] in tokens
            or item["original"] in originals
        ):
            raise SafetyError("Document restoration bundle is malformed.")
        tokens.add(item["token"])
        originals.add(item["original"])
    return value


def encrypt_document_bundle(bundle: dict, passphrase: str) -> bytes:
    validate_document_bundle(bundle)
    salt = os.urandom(16)
    payload = json.dumps(bundle, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    encrypted = MAGIC + salt + _fernet(passphrase, salt).encrypt(payload)
    if len(encrypted) > MAP_LIMIT:
        raise SafetyError("Document restoration bundle exceeds the supported size limit.")
    return encrypted


def decrypt_document_bundle(data: bytes, passphrase: str) -> dict:
    if len(data) > MAP_LIMIT or not data.startswith(MAGIC) or len(data) < len(MAGIC) + 17:
        raise SafetyError("Document restoration bundle version or envelope is unsupported.")
    salt = data[len(MAGIC) : len(MAGIC) + 16]
    try:
        payload = _fernet(passphrase, salt).decrypt(data[len(MAGIC) + 16 :])
        return validate_document_bundle(
            json.loads(payload, object_pairs_hook=_unique_object)
        )
    except (InvalidToken, UnicodeError, ValueError, RecursionError, TypeError):
        raise SafetyError(
            "Document restoration bundle could not be authenticated or decoded."
        ) from None


def read_document_bundle(path: Path, passphrase: str, *context: Path) -> dict:
    try:
        resolved = check_map_read(path, *context)
        return decrypt_document_bundle(read_bounded(resolved, MAP_LIMIT), passphrase)
    except OSError:
        raise SafetyError("Unable to access private document restoration bundle.") from None
