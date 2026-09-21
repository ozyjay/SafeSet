"""Safety checks for the desktop controller without requiring a display server."""

from pathlib import Path

import pytest

from safeset.desktop_flow import approve_export, prepare_export, restore_results
from safeset.errors import SafetyError
from safeset.ingestion import read_csv

from .conftest import PASSPHRASE, ROOT


def test_review_does_not_publish_and_requires_approval(destinations):
    output, mapping = destinations
    review = prepare_export(
        ROOT / "examples/synthetic_students.csv",
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
    source = tmp_path / "synthetic-invalid.csv"
    source.write_text(
        (ROOT / "examples/synthetic_students.csv").read_text().replace("Moon", "Unapproved")
    )
    review = prepare_export(source, ROOT / "examples/example-policy.yaml", output, mapping)
    assert not review.validation.passed
    with pytest.raises(SafetyError, match="Validation failed"):
        approve_export(review, PASSPHRASE, approved=True)
    assert not output.exists() and not mapping.exists()


def test_desktop_flow_synthetic_round_trip(destinations):
    output, mapping = destinations
    review = prepare_export(
        ROOT / "examples/synthetic_students.csv",
        ROOT / "examples/example-policy.yaml",
        output,
        mapping,
    )
    approve_export(review, PASSPHRASE, approved=True)
    assert output.exists() and mapping.exists()
    restored = output.parent.parent / "private/restored.csv"
    columns = ("campus", "subject", "gpa")
    with pytest.raises(SafetyError, match="authorisation"):
        restore_results(output, mapping, restored, columns, PASSPHRASE, authorised=False)
    assert not restored.exists()
    assert restore_results(output, mapping, restored, columns, PASSPHRASE, authorised=True) == 4
    assert read_csv(restored).rows[0]["student_number"] == "SYNTH-001"


def test_map_must_be_separate_before_review(destinations):
    output, _ = destinations
    with pytest.raises(SafetyError, match="separate"):
        prepare_export(
            ROOT / "examples/synthetic_students.csv",
            ROOT / "examples/example-policy.yaml",
            output,
            Path(output.parent / "map.enc"),
        )
    assert not output.exists()
