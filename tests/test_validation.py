from copy import deepcopy

import pytest

from safeset.errors import SafetyError
from safeset.ingestion import Table
from safeset.validation import validate
from safeset.workflow import export_candidate

from .conftest import PASSPHRASE, ROOT


def test_group_metrics(candidate, policy):
    report = validate(candidate.table, policy)
    assert report.passed
    assert report.minimum_class_size == 2
    assert report.unique_records == report.small_class_records == report.small_cells == 0
    assert report.classifications["record_id"] == "pseudonymous_identifier"


@pytest.mark.parametrize(
    "mode",
    [
        "extra",
        "missing",
        "prose",
        "identifier",
        "blank",
        "duplicate",
        "malformed",
        "small_joint",
        "numeric_out_of_bounds",
        "numeric_precision",
        "numeric_formatting",
        "empty",
    ],
)
def test_validation_rejects(candidate, policy, mode):
    columns = candidate.table.columns
    rows = deepcopy(candidate.table.rows)
    if mode == "extra":
        columns = (*columns, "unknown")
        rows = tuple({**r, "unknown": "x"} for r in rows)
    elif mode == "missing":
        columns = columns[:-1]
    elif mode == "prose":
        rows[0]["campus"] = "This is private invented personal prose"
    elif mode == "identifier":
        rows[0]["campus"] = "invented@example.invalid"
    elif mode == "blank":
        rows[0]["campus"] = ""
    elif mode == "duplicate":
        rows[0]["record_id"] = rows[1]["record_id"]
    elif mode == "malformed":
        rows[0]["record_id"] = "not-a-valid-uuid"
    elif mode == "small_joint":
        # Marginals remain size 2, but every joint combination becomes unique.
        rows[0]["gpa"], rows[2]["gpa"] = rows[2]["gpa"], rows[0]["gpa"]
    elif mode == "numeric_out_of_bounds":
        rows[0]["gpa"] = "7.1"
    elif mode == "numeric_precision":
        rows[0]["gpa"] = "4.123"
    elif mode == "numeric_formatting":
        rows[0]["gpa"] = "04.20"
    else:
        rows = ()
    report = validate(Table(columns, rows), policy)
    assert not report.passed
    if mode == "small_joint":
        assert report.small_cells == 0
        assert report.unique_fraction == 1
        assert report.small_class_records == 4


def test_failed_validation_writes_nothing(candidate, policy, destinations):
    candidate.table.rows[0]["campus"] = "not-approved"
    output, map_path = destinations
    with pytest.raises(SafetyError):
        export_candidate(
            candidate,
            policy,
            output,
            map_path,
            PASSPHRASE,
            approved=True,
            create_map=True,
            source_path=ROOT / "examples/synthetic_students.xlsx",
        )
    assert not output.exists() and not map_path.exists()


def test_controlled_profile_reports_rare_groups_without_structural_bypass(candidate, policy):
    rows = deepcopy(candidate.table.rows)
    rows[0]["gpa"], rows[2]["gpa"] = rows[2]["gpa"], rows[0]["gpa"]
    report = validate(Table(candidate.table.columns, rows), policy, "controlled_pseudonymisation")
    assert report.passed
    assert report.small_class_records == 4
    assert any("Controlled pseudonymisation risk" in warning for warning in report.warnings)
    rows[0]["campus"] = "not-approved"
    assert not validate(
        Table(candidate.table.columns, rows), policy, "controlled_pseudonymisation"
    ).passed


@pytest.mark.parametrize(
    "column,classification",
    [
        ("student_name", "direct_identifier"),
        ("notes", "free_text"),
        ("unclassified", "unknown"),
    ],
)
def test_rejected_fields_distinguished_without_echoing_values(
    candidate, policy, column, classification
):
    table = Table(
        (*candidate.table.columns, column),
        tuple({**r, column: "private-synthetic-value"} for r in candidate.table.rows),
    )
    report = validate(table, policy)
    assert not report.passed
    assert report.rejected_field_classes == {classification: 1}
    assert "private-synthetic-value" not in str(report.summary())
