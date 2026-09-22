from copy import deepcopy

import pytest

from safeset.errors import SafetyError
from safeset.ingestion import Table
from safeset.mapping import decrypt_mapping, encrypt_mapping, validate_mapping
from safeset.policy import parse_policy
from safeset.pseudonyms import new_id
from safeset.restoration import restore
from safeset.transform import sanitise

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


def test_spaced_headings_round_trip_with_explicit_result_allowlist():
    policy = parse_policy(
        {
            "version": 2,
            "min_group_size": 2,
            "columns": {
                "Student Number": {
                    "action": "pseudonymise",
                    "classification": "direct_identifier",
                },
                "Campus Location": {
                    "action": "keep",
                    "classification": "quasi_identifier",
                    "allowed_values": ["Moon"],
                },
            },
        }
    )
    source = Table(
        ("Student Number", "Campus Location"),
        (
            {"Student Number": "SYNTH-001", "Campus Location": "Moon"},
            {"Student Number": "SYNTH-002", "Campus Location": "Moon"},
        ),
    )
    candidate = sanitise(source, policy)
    mapping = decrypt_mapping(encrypt_mapping(candidate.mapping, PASSPHRASE), PASSPHRASE)
    analysed = Table(
        ("record_id", "Allocation Result"),
        tuple(
            {"record_id": row["record_id"], "Allocation Result": "Invented Team"}
            for row in candidate.table.rows
        ),
    )
    restored = restore(analysed, mapping, ("Allocation Result",))
    assert restored.columns == ("Student Number", "Allocation Result")
    assert [row["Student Number"] for row in restored.rows] == ["SYNTH-001", "SYNTH-002"]
