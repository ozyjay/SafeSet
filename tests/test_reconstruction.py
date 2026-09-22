"""Synthetic version 2 working-copy round trip and failure cases."""

import socket
from copy import deepcopy

import pytest
from typer.testing import CliRunner

from safeset.bundle import decrypt_bundle, encrypt_bundle
from safeset.cli import app
from safeset.desktop_flow import (
    approve_protection,
    approve_reconstruction,
    prepare_protection,
    prepare_reconstruction,
)
from safeset.errors import SafetyError
from safeset.ingestion import Table, excel_bytes, read_excel
from safeset.policy_authoring import load_drafts
from safeset.pseudonyms import new_id
from safeset.reconstruction import reconstruct

from .conftest import PASSPHRASE, ROOT


def _prepared(destinations):
    source = ROOT / "examples/synthetic_students.xlsx"
    drafts, threshold = load_drafts(source, ROOT / "examples/example-policy.yaml")
    output, bundle = destinations
    review = prepare_protection(source, drafts, str(threshold), output, bundle)
    assert review.validation.passed
    approve_protection(review, PASSPHRASE, approved=True)
    return source, output, bundle


def test_reconstruction_round_trip(destinations):
    source, output, bundle_path = _prepared(destinations)
    protected = read_excel(output)
    assert "student_name" not in protected.columns
    assert "student_number" not in protected.columns
    rows = tuple({**row, "Team": "Robot Team"} for row in protected.rows)
    returned_path = output.parent / "analysed.xlsx"
    returned_path.write_bytes(excel_bytes(Table((*protected.columns, "Team"), rows)))
    restored_path = output.parent.parent / "private/restored.xlsx"
    review = prepare_reconstruction(returned_path, source, bundle_path, restored_path, PASSPHRASE)
    assert review.new_columns == ("Team",)
    with pytest.raises(SafetyError):
        approve_reconstruction(review, (), authorised=True)
    assert approve_reconstruction(review, ("Team",), authorised=True) == 4
    original = read_excel(source)
    restored = read_excel(restored_path)
    assert restored.columns == (*original.columns, "Team")
    assert all(row["Team"] == "Robot Team" for row in restored.rows)
    assert [tuple(row[c] for c in original.columns) for row in restored.rows] == [
        tuple(row[c] for c in original.columns) for row in original.rows
    ]
    with pytest.raises(SafetyError):
        approve_reconstruction(review, ("Team",), authorised=True)


@pytest.mark.parametrize(
    "change", ["duplicate", "missing", "unknown", "malformed", "changed", "extra"]
)
def test_reconstruction_rejects_tampering(destinations, change):
    source, output, bundle_path = _prepared(destinations)
    from safeset.bundle import read_bundle

    bundle = read_bundle(bundle_path, PASSPHRASE)
    protected = read_excel(output)
    rows = [dict(row) for row in protected.rows]
    columns = protected.columns
    if change == "duplicate":
        rows[0]["record_id"] = rows[1]["record_id"]
    elif change == "missing":
        rows.pop()
    elif change == "unknown":
        rows[0]["record_id"] = new_id()
    elif change == "malformed":
        rows[0]["record_id"] = "bad-id"
    elif change == "changed":
        rows[0]["campus"] = new_id()
    else:
        columns = (*columns, "student_name")
        rows = [{**row, "student_name": "Invented Person"} for row in rows]
    with pytest.raises(SafetyError):
        reconstruct(read_excel(source), Table(columns, tuple(rows)), bundle, ())


def test_wrong_source_and_legacy_map_rejected(destinations):
    source, output, bundle_path = _prepared(destinations)
    from safeset.bundle import read_bundle

    bundle = read_bundle(bundle_path, PASSPHRASE)
    original = read_excel(source)
    rows = deepcopy(original.rows)
    rows[0]["student_name"] = "Invented Changed"
    with pytest.raises(SafetyError, match="source does not match"):
        reconstruct(Table(original.columns, rows), read_excel(output), bundle, ())
    with pytest.raises(SafetyError):
        decrypt_bundle(b"SAFESET1\n" + bundle_path.read_bytes()[9:], PASSPHRASE)
    ciphertext = encrypt_bundle(bundle, PASSPHRASE)
    assert decrypt_bundle(ciphertext, PASSPHRASE) == bundle
    with pytest.raises(SafetyError):
        decrypt_bundle(ciphertext[:-1] + b"!", PASSPHRASE)


def test_bundle_is_minimal_and_runtime_offline(destinations, monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("Runtime attempted a network connection")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    source, output, bundle_path = _prepared(destinations)
    from safeset.bundle import read_bundle

    bundle = read_bundle(bundle_path, PASSPHRASE)
    assert set(bundle) == {
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
    assert set(bundle["codebooks"]) == {"campus", "subject"}
    encoded = str(bundle)
    for row in read_excel(source).rows:
        assert row["student_name"] not in encoded
        assert row["email"] not in encoded
        assert row["notes"] not in encoded
        assert row["student_number"].encode() not in bundle_path.read_bytes()
    assert "student_number" not in read_excel(output).columns


def test_source_change_after_review_blocks_publication(destinations, tmp_path):
    source = tmp_path / "source.xlsx"
    original = read_excel(ROOT / "examples/synthetic_students.xlsx")
    source.write_bytes(excel_bytes(original))
    drafts, threshold = load_drafts(source, ROOT / "examples/example-policy.yaml")
    output, bundle = destinations
    review = prepare_protection(source, drafts, str(threshold), output, bundle)
    rows = deepcopy(original.rows)
    rows[0]["student_name"] = "Invented Change"
    source.write_bytes(excel_bytes(Table(original.columns, rows)))
    with pytest.raises(SafetyError, match="changed"):
        approve_protection(review, PASSPHRASE, approved=True)
    assert not output.exists() and not bundle.exists()


def test_cli_protect_and_reconstruct(destinations, monkeypatch):
    monkeypatch.setattr("safeset.cli.secret", lambda **_kwargs: PASSPHRASE)
    output, bundle_path = destinations
    source = ROOT / "examples/synthetic_students.xlsx"
    runner = CliRunner()
    protected = runner.invoke(
        app,
        [
            "protect",
            str(source),
            "--policy",
            str(ROOT / "examples/example-policy.yaml"),
            "--output",
            str(output),
            "--create-bundle",
            "--bundle",
            str(bundle_path),
            "--approve-export",
        ],
    )
    assert protected.exit_code == 0, protected.output
    table = read_excel(output)
    returned = output.parent / "with-results.xlsx"
    returned.write_bytes(
        excel_bytes(
            Table(
                (*table.columns, "Team"),
                tuple({**row, "Team": "Robot Team"} for row in table.rows),
            )
        )
    )
    restored = output.parent.parent / "private/reconstructed.xlsx"
    missing_approval = runner.invoke(
        app,
        [
            "reconstruct",
            str(returned),
            "--original-source",
            str(source),
            "--bundle",
            str(bundle_path),
            "--output",
            str(restored),
            "--authorise",
        ],
    )
    assert missing_approval.exit_code != 0
    assert not restored.exists()
    result = runner.invoke(
        app,
        [
            "reconstruct",
            str(returned),
            "--original-source",
            str(source),
            "--bundle",
            str(bundle_path),
            "--output",
            str(restored),
            "--result-column",
            "Team",
            "--authorise",
        ],
    )
    assert result.exit_code == 0, result.output
    assert read_excel(restored).columns == (*read_excel(source).columns, "Team")
