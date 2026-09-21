from copy import deepcopy

import pytest

from safeset.errors import SafetyError
from safeset.ingestion import Table
from safeset.mapping import decrypt_mapping, encrypt_mapping, validate_mapping
from safeset.pseudonyms import new_id
from safeset.restoration import restore

from .conftest import PASSPHRASE


def test_real_encryption_and_authentication(candidate):
    encrypted = encrypt_mapping(candidate.mapping, PASSPHRASE)
    assert decrypt_mapping(encrypted, PASSPHRASE) == candidate.mapping
    assert encrypted != encrypt_mapping(candidate.mapping, PASSPHRASE)
    for bad in [
        encrypted[:-10],
        b"broken",
        encrypted[:-1] + b"!",
        encrypted[:13] + bytes([encrypted[13] ^ 1]) + encrypted[14:],
    ]:
        with pytest.raises(SafetyError):
            decrypt_mapping(bad, PASSPHRASE)
    with pytest.raises(SafetyError):
        decrypt_mapping(encrypted, "wrong-synthetic-passphrase")
    with pytest.raises(SafetyError):
        encrypt_mapping(candidate.mapping, "short")


@pytest.mark.parametrize(
    "mode",
    ["duplicate", "missing", "unknown", "malformed", "extra", "collision", "formula", "control"],
)
def test_restore_rejects(candidate, mode):
    rows = deepcopy(candidate.table.rows)
    columns = candidate.table.columns
    allowed = ("campus", "subject", "gpa")
    if mode == "duplicate":
        rows[0]["record_id"] = rows[1]["record_id"]
    elif mode == "missing":
        rows = rows[:-1]
    elif mode == "unknown":
        rows[0]["record_id"] = new_id()
    elif mode == "malformed":
        rows[0]["record_id"] = "malformed-id"
    elif mode == "extra":
        columns = (*columns, "unexpected")
    elif mode == "collision":
        allowed = (*allowed, "student_number")
    elif mode == "formula":
        rows[0]["campus"] = '=WEBSERVICE("https://example.invalid")'
    else:
        rows[0]["campus"] = "Moon\tprivate"
    with pytest.raises(SafetyError):
        restore(Table(columns, rows), candidate.mapping, allowed)


@pytest.mark.parametrize(
    "mode", ["empty", "duplicate_identity", "malformed_id", "extra", "wrong_version"]
)
def test_mapping_structure_rejects(candidate, mode):
    mapping = deepcopy(candidate.mapping)
    ids = list(mapping["records"])
    if mode == "empty":
        mapping["records"] = {}
    elif mode == "duplicate_identity":
        mapping["records"][ids[0]] = mapping["records"][ids[1]]
    elif mode == "malformed_id":
        mapping["records"]["bad"] = mapping["records"].pop(ids[0])
    elif mode == "extra":
        mapping["names"] = ["must-not-be-in-map"]
    else:
        mapping["version"] = True
    with pytest.raises(SafetyError):
        validate_mapping(mapping)
