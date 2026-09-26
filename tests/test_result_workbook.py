"""Synthetic result-only workbook restoration and identity-integrity checks."""

import socket
from types import SimpleNamespace

import pytest

from safeset.desktop_bridge import Bridge
from safeset.desktop_flow import approve_relational_protection, prepare_relational_protection
from safeset.errors import SafetyError
from safeset.ingestion import Table, excel_workbook_bytes, list_excel_sheets, read_excel_sheets
from safeset.result_workbook import (
    approve_result_workbook,
    prepare_result_workbook,
    update_result_workbook,
)

from . import test_workbook_editing as editing_support
from .conftest import PASSPHRASE
from .test_desktop_bridge import call

editing = editing_support.editing


def result_input(files, mutate=None, *, include_record_id=False):
    protected = read_excel_sheets(files.protected, ("Allocations", "Participants"))
    members = protected["Participants"].rows
    rows = [
        {"entity_id": members[0]["entity_id"], "team": members[0]["team"], "role": "Lead"},
        {"entity_id": members[1]["entity_id"], "team": members[1]["team"], "role": "Member"},
        {"entity_id": members[2]["entity_id"], "team": "Synthetic New Team", "role": "Member"},
    ]
    if include_record_id:
        for row, member in zip(rows, members, strict=True):
            row["record_id"] = member["record_id"]
    if mutate:
        mutate(rows, protected)
    columns = ("entity_id", "record_id", "team", "role") if include_record_id else (
        "entity_id", "team", "role"
    )
    files.returned.write_bytes(
        excel_workbook_bytes(
            {
                "New Allocations": Table(columns, tuple(rows)),
                "Team Summary": Table(
                    ("team", "count"), ({"team": "Synthetic New Team", "count": "1"},)
                ),
            }
        )
    )


def prepare(files):
    return prepare_result_workbook(
        files.returned, files.source, files.bundle, files.restored, PASSPHRASE
    )


def join():
    return {
        "New Allocations": {
            "source_sheet": "Participants",
            "source_fields": ["student_key"],
            "join_by": "entity_id",
            "unique_entities": True,
        }
    }


def approvals(review):
    fields = {name: info["result_fields"] for name, info in review.summary["sheets"].items()}
    categories = {
        name: list(info["new_categories"]) for name, info in review.summary["sheets"].items()
    }
    return fields, categories


def test_result_only_workbook_restores_known_entities_and_new_teams(editing, monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("Network attempted"))
    result_input(editing)
    review = prepare(editing)
    assert not review.summary["ready"]
    assert set(review.summary["sheets"]) == {"New Allocations", "Team Summary"}
    assert review.summary["sheets"]["New Allocations"]["new_categories"]["team"] == 1
    ready = update_result_workbook(review, join())
    assert ready.summary["ready"]
    fields, categories = approvals(ready)
    with pytest.raises(SafetyError, match="Review every result"):
        approve_result_workbook(ready, fields, {}, ["New Allocations"], authorised=True)
    with pytest.raises(SafetyError, match="Review every result"):
        approve_result_workbook(ready, fields, categories, [], authorised=True)
    assert approve_result_workbook(
        ready, fields, categories, ["New Allocations"], authorised=True
    ) == 4
    restored = read_excel_sheets(editing.restored, ("New Allocations", "Team Summary"))
    assert list_excel_sheets(editing.restored) == ("New Allocations", "Team Summary")
    assert restored["New Allocations"].columns == ("student_key", "team", "role")
    assert [row["student_key"] for row in restored["New Allocations"].rows] == [
        "SYNTH-001", "SYNTH-002", "SYNTH-003"
    ]
    assert restored["New Allocations"].rows[0]["team"] == "Synthetic Alpha"
    assert restored["New Allocations"].rows[2]["team"] == "Synthetic New Team"
    assert restored["Team Summary"].columns == ("team", "count")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows, _: rows[0].update(entity_id="unknown"),
        lambda rows, _: rows[0].update(entity_id=rows[1]["entity_id"]),
        lambda rows, _: rows[0].update(team="00000000-0000-4000-8000-000000000001"),
        lambda rows, _: rows[0].update(team="00000000-0000-1000-8000-000000000001"),
        lambda rows, _: rows[0].update(role="=FORMULA()"),
    ],
)
def test_invalid_result_identity_or_value_fails(editing, mutate):
    result_input(editing, mutate)
    with pytest.raises(SafetyError):
        review = prepare(editing)
        update_result_workbook(review, join())
    assert not editing.restored.exists()


def test_result_review_detects_stale_returned_workbook(editing):
    result_input(editing)
    ready = update_result_workbook(prepare(editing), join())
    result_input(editing, lambda rows, _: rows[0].update(role="Observer"))
    fields, categories = approvals(ready)
    with pytest.raises(SafetyError, match="changed after"):
        approve_result_workbook(ready, fields, categories, ["New Allocations"], authorised=True)
    assert not editing.restored.exists()


def test_exact_record_join_and_record_entity_mismatch(editing):
    result_input(editing, include_record_id=True)
    review = prepare(editing)
    options = join()
    options["New Allocations"]["join_by"] = "record_id"
    ready = update_result_workbook(review, options)
    fields, categories = approvals(ready)
    approve_result_workbook(ready, fields, categories, ["New Allocations"], authorised=True)
    restored = read_excel_sheets(editing.restored, ("New Allocations",))["New Allocations"]
    assert restored.columns == ("student_key", "team", "role")


def test_mismatched_record_id_blocks_result(editing):
    result_input(
        editing,
        lambda rows, _: rows[0].update(record_id=rows[1]["record_id"]),
        include_record_id=True,
    )
    with pytest.raises(SafetyError, match="structure, identities"):
        prepare(editing)
    assert not editing.restored.exists()


def test_duplicate_result_entity_requires_explicit_multiple_row_choice(editing):
    result_input(editing, lambda rows, _: rows[0].update(entity_id=rows[1]["entity_id"]))
    review = prepare(editing)
    with pytest.raises(SafetyError, match="structure, identities"):
        update_result_workbook(review, join())
    multiple = join()
    multiple["New Allocations"]["unique_entities"] = False
    ready = update_result_workbook(review, multiple)
    assert ready.summary["ready"]


def test_missing_or_colliding_source_join_blocks_restoration(editing):
    result_input(editing)
    review = prepare(editing)
    missing = join()
    missing["New Allocations"]["source_sheet"] = "Allocations"
    with pytest.raises(SafetyError, match="source-field selections"):
        update_result_workbook(review, missing)
    collision = join()
    collision["New Allocations"]["source_fields"] = ["team"]
    with pytest.raises(SafetyError, match="source-field selections"):
        update_result_workbook(review, collision)
    assert not editing.restored.exists()


def test_original_change_after_review_blocks_publication(editing):
    result_input(editing)
    ready = update_result_workbook(prepare(editing), join())
    editing.source.write_bytes(editing.source.read_bytes() + b"synthetic-stale")
    fields, categories = approvals(ready)
    with pytest.raises(SafetyError, match="changed after"):
        approve_result_workbook(
            ready, fields, categories, ["New Allocations"], authorised=True
        )
    assert not editing.restored.exists()


def test_result_bridge_review_does_not_expose_identity_values(editing):
    result_input(editing)
    bridge = Bridge()
    first = call(
        bridge,
        "prepare_result_workbook",
        {
            "returned": str(editing.returned),
            "source": str(editing.source),
            "bundle": str(editing.bundle),
            "output": str(editing.restored),
            "passphrase": PASSPHRASE,
        },
    )
    assert first["ok"] is True
    first = first["result"]
    assert first["ready"] is False
    assert "SYNTH-001" not in str(first)
    assert "Synthetic New Team" not in str(first)
    invalid = join()
    invalid["New Allocations"]["source_fields"] = ["team"]
    rejected = call(
        bridge, "update_result_workbook", {"review_id": first["review_id"], "joins": invalid}
    )
    assert rejected["ok"] is False and rejected["error"] == "result_workbook_join"
    again = call(
        bridge,
        "prepare_result_workbook",
        {
            "returned": str(editing.returned),
            "source": str(editing.source),
            "bundle": str(editing.bundle),
            "output": str(editing.restored),
            "passphrase": PASSPHRASE,
        },
    )
    assert again["ok"] is True
    first = again["result"]
    updated = call(
        bridge, "update_result_workbook", {"review_id": first["review_id"], "joins": join()}
    )
    assert updated["ok"] is True
    updated = updated["result"]
    assert updated["ready"] is True
    assert "SYNTH-001" not in str(updated)
    fields = {name: info["result_fields"] for name, info in updated["sheets"].items()}
    categories = {name: list(info["new_categories"]) for name, info in updated["sheets"].items()}
    done = call(
        bridge,
        "approve_result_workbook",
        {
            "review_id": updated["review_id"],
            "approved_fields": fields,
            "approved_categories": categories,
            "approved_joins": ["New Allocations"],
        },
    )
    assert done["ok"] is True
    assert done["result"] == {"created": True, "rows": 4}


def test_version_three_bundle_supports_result_only_workbook(editing):
    protected = editing.protected.parent / "synthetic-v3-protected.xlsx"
    bundle = editing.bundle.parent / "synthetic-v3.enc"
    review = prepare_relational_protection(
        editing.source,
        tuple(editing.drafts),
        editing.drafts,
        "2",
        protected,
        bundle,
        "controlled_pseudonymisation",
        ("team",),
    )
    approve_relational_protection(review, PASSPHRASE, approved=True)
    files = SimpleNamespace(
        source=editing.source,
        protected=protected,
        bundle=bundle,
        returned=editing.returned,
        restored=editing.restored,
    )
    result_input(files)
    ready = update_result_workbook(prepare(files), join())
    fields, categories = approvals(ready)
    assert approve_result_workbook(
        ready, fields, categories, ["New Allocations"], authorised=True
    ) == 4
