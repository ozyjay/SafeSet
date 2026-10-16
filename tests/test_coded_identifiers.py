"""Invented identities only: additional identifiers never leave as source labels."""

from copy import deepcopy

import pytest

from safeset.bundle import create_bundle, decrypt_bundle, encrypt_bundle
from safeset.errors import SafetyError
from safeset.ingestion import Table, excel_bytes
from safeset.policy import parse_policy
from safeset.policy_authoring import RuleDraft, policy_payload
from safeset.reconstruction import reconstruct
from safeset.relational import (
    create_relational_bundle,
    reconstruct_relational,
    sanitise_relational,
    validate_relational,
)
from safeset.transform import sanitise
from safeset.validation import validate
from safeset.workbook_editing import validate_editable_fields

from .conftest import PASSPHRASE


def fixture():
    names = ("Synthetic Ada", "Synthetic Ada", "Synthetic Bea", "Synthetic Bea")
    source = Table(
        ("Synthetic key", "Student Name"),
        tuple(
            {"Synthetic key": f"SYNTH-{i:03}", "Student Name": name} for i, name in enumerate(names)
        ),
    )
    raw = policy_payload(
        {
            "Synthetic key": RuleDraft("pseudonymise"),
            # Existing desktop decisions migrate by explicit code action, not by retaining names.
            "Student Name": RuleDraft("code", "analytical_attribute", tuple(sorted(set(names)))),
        },
        "2",
    )
    return source, raw


def test_coded_name_is_separate_random_reference_and_encrypted_round_trip():
    source, raw = fixture()
    assert raw["version"] == 5
    policy = parse_policy(raw)
    assert policy.columns["Student Name"].classification == "direct_identifier"
    first, second = sanitise(source, policy), sanitise(source, policy)
    codes = [row["Student Name"] for row in first.table.rows]
    assert codes[0] == codes[1] and codes[2] == codes[3] and codes[0] != codes[2]
    assert set(codes).isdisjoint(first.mapping["records"])
    assert set(codes).isdisjoint(row["Student Name"] for row in second.table.rows)
    assert first.mapping["source_column"] == "Synthetic key"
    assert set(first.mapping) == {"version", "source_column", "records"}
    assert all("Synthetic" not in value for row in first.table.rows for value in row.values())
    report = validate(first.table, policy)
    assert report.passed and report.minimum_class_size == 2
    assert report.classifications["Student Name"] == "pseudonymous_identifier"
    assert any("namesakes" in message for message in report.warnings)
    bundle = create_bundle(source, policy, first)
    encoded = encrypt_bundle(bundle, PASSPHRASE)
    assert b"Synthetic Ada" not in encoded and b"Synthetic Bea" not in encoded
    bundle = decrypt_bundle(encoded, PASSPHRASE)
    assert reconstruct(source, first.table, bundle, ()) == source
    changed = Table(
        first.table.columns,
        tuple(
            {**row, "Student Name": codes[2] if i == 0 else row["Student Name"]}
            for i, row in enumerate(first.table.rows)
        ),
    )
    with pytest.raises(SafetyError):
        reconstruct(source, changed, bundle, ())
    leaked = Table(
        first.table.columns,
        tuple(
            {**row, "Student Name": source.rows[i]["Student Name"]}
            for i, row in enumerate(first.table.rows)
        ),
    )
    assert not validate(leaked, policy).passed
    # XLSX values are checked structurally above; export has only generated codes.
    assert excel_bytes(first.table)


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_old_versions_do_not_gain_identifier_coding(version):
    _, raw = fixture()
    raw["version"] = version
    with pytest.raises(SafetyError):
        parse_policy(raw)


@pytest.mark.parametrize("action", ["keep", "bin", "keep_numeric", "review_text"])
def test_original_identifiers_still_cannot_be_retained(action):
    _, raw = fixture()
    config = {"action": action, "classification": "analytical_attribute"}
    config.update(
        {
            "keep": {"allowed_values": ["Synthetic Ada"]},
            "bin": {"bins": [[0, 1], [1, 2]]},
            "keep_numeric": {"bounds": [0, 10]},
            "review_text": {"classification": "free_text", "text_reviews": {}},
        }[action]
    )
    raw["columns"]["Student Name"] = config
    with pytest.raises(SafetyError):
        parse_policy(raw)


def test_explicit_classification_source_domain_and_source_key_remain_required():
    source, raw = fixture()
    for change in ("classification", "domain", "key", "unknown"):
        broken = deepcopy(raw)
        if change == "classification":
            broken["columns"]["Student Name"]["classification"] = "analytical_attribute"
        elif change == "domain":
            broken["columns"]["Student Name"]["allowed_values"] = ["Synthetic Ada"]
        elif change == "key":
            broken["columns"]["Synthetic key"]["action"] = "drop"
        else:
            broken["columns"]["Student Name"]["override"] = True
        with pytest.raises(SafetyError):
            sanitise(source, parse_policy(broken))


def test_coded_identifiers_remain_in_joint_and_linked_checks_and_are_not_editable():
    source, raw = fixture()
    policy = parse_policy(raw)
    sources, policies = {"Invented sheet": source}, {"Invented sheet": policy}
    candidate = sanitise_relational(sources, policies)
    assert validate_relational(candidate, policies).passed
    bundle = create_relational_bundle(sources, policies, candidate, "strict")
    assert (
        reconstruct_relational(sources, candidate.tables, bundle, {"Invented sheet": ()}) == sources
    )
    with pytest.raises(SafetyError):
        validate_editable_fields({"Invented sheet": ["Student Name"]}, policies)
    unique = Table(
        source.columns,
        tuple(
            {**row, "Student Name": f"Synthetic Person {i}"} for i, row in enumerate(source.rows)
        ),
    )
    raw["columns"]["Student Name"]["allowed_values"] = [r["Student Name"] for r in unique.rows]
    policy = parse_policy(raw)
    candidate = sanitise(unique, policy)
    assert not validate(candidate.table, policy).passed
    assert validate(candidate.table, policy, "controlled_pseudonymisation").passed
    linked = sanitise_relational({"Invented sheet": unique}, {"Invented sheet": policy})
    assert not validate_relational(linked, {"Invented sheet": policy}).passed
