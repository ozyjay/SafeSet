"""Safety checks for the desktop controller without requiring a display server."""

from pathlib import Path

import pytest

from safeset.desktop_flow import approve_export, inspect_returned, prepare_export, restore_results
from safeset.errors import SafetyError
from safeset.ingestion import Table, excel_bytes, read_excel

from .conftest import PASSPHRASE, ROOT


def test_review_does_not_publish_and_requires_approval(destinations):
    output, mapping = destinations
    review = prepare_export(
        ROOT / "examples/synthetic_students.xlsx",
        ROOT / "examples/example-policy.yaml",
        output,
        mapping,
    )
    assert review.validation.passed
    assert not output.exists() and not mapping.exists()
    with pytest.raises(SafetyError, match="approval"):
        approve_export(review, PASSPHRASE, approved=False)
    assert not output.exists() and not mapping.exists()


def test_failed_review_cannot_export(destinations, tmp_path):
    output, mapping = destinations
    source = tmp_path / "synthetic-invalid.xlsx"
    original = read_excel(ROOT / "examples/synthetic_students.xlsx")
    rows = tuple(
        {**row, "gpa": "5.2"} if index == 0 else row for index, row in enumerate(original.rows)
    )
    source.write_bytes(excel_bytes(Table(original.columns, rows)))
    review = prepare_export(source, ROOT / "examples/example-policy.yaml", output, mapping)
    assert not review.validation.passed
    with pytest.raises(SafetyError, match="Validation failed"):
        approve_export(review, PASSPHRASE, approved=True)
    assert not output.exists() and not mapping.exists()


def test_desktop_flow_synthetic_round_trip(destinations):
    output, mapping = destinations
    review = prepare_export(
        ROOT / "examples/synthetic_students.xlsx",
        ROOT / "examples/example-policy.yaml",
        output,
        mapping,
    )
    approve_export(review, PASSPHRASE, approved=True)
    assert output.exists() and mapping.exists()
    restored = output.parent.parent / "private/restored.xlsx"
    columns = ("campus", "subject", "gpa")
    with pytest.raises(SafetyError, match="authorisation"):
        restore_results(output, mapping, restored, columns, PASSPHRASE, authorised=False)
    assert not restored.exists()
    assert restore_results(output, mapping, restored, columns, PASSPHRASE, authorised=True) == 4
    assert read_excel(restored).rows[0]["student_number"] == "SYNTH-001"


def test_map_must_be_separate_before_review(destinations):
    output, _ = destinations
    with pytest.raises(SafetyError, match="separate"):
        prepare_export(
            ROOT / "examples/synthetic_students.xlsx",
            ROOT / "examples/example-policy.yaml",
            output,
            Path(output.parent / "map.enc"),
        )
    assert not output.exists()


def test_returned_review_shows_headings_and_counts_only(candidate, tmp_path):
    returned = Table(
        ("record_id", "team"),
        tuple(
            {"record_id": row["record_id"], "team": "Invented Team"} for row in candidate.table.rows
        ),
    )
    path = tmp_path / "returned.xlsx"
    path.write_bytes(excel_bytes(returned))
    review = inspect_returned(path)
    assert review.rows == 4
    assert review.result_columns == ("team",)
    assert "Invented Team" not in str(review)


def test_returned_review_rejects_bad_ids_before_passphrase(candidate, tmp_path):
    returned = Table(
        ("record_id", "team"),
        tuple(
            {"record_id": "private-invalid-id" if i == 0 else row["record_id"], "team": "A"}
            for i, row in enumerate(candidate.table.rows)
        ),
    )
    path = tmp_path / "returned.xlsx"
    path.write_bytes(excel_bytes(returned))
    with pytest.raises(SafetyError) as caught:
        inspect_returned(path)
    assert "private-invalid-id" not in str(caught.value)
