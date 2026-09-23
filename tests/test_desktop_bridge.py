"""Synthetic protocol and local round-trip tests for the macOS helper."""

import json
import socket

import pytest

from safeset.desktop_bridge import Bridge
from safeset.errors import SafetyError
from safeset.ingestion import Table, excel_bytes, list_excel_sheets, read_excel
from safeset.policy_authoring import load_drafts

from .conftest import PASSPHRASE, ROOT


def call(bridge: Bridge, command: str, payload: dict, request_id: str = "test") -> dict:
    encoded = (
        json.dumps(
            {"version": 1, "id": request_id, "command": command, "payload": payload}
        ).encode()
        + b"\n"
    )
    return json.loads(bridge.process_line(encoded))


def draft_payload():
    source = ROOT / "examples/synthetic_students.xlsx"
    drafts, threshold = load_drafts(source, ROOT / "examples/example-policy.yaml")
    return {
        name: {
            "action": d.action,
            "classification": d.classification,
            "allowed_values": list(d.allowed_values),
            "bins": [list(p) for p in d.bins],
            "bounds": list(d.bounds) if d.bounds is not None else None,
        }
        for name, d in drafts.items()
    }, str(threshold)


def test_protocol_rejects_malformed_and_secret_output():
    bridge = Bridge()
    for line in (
        b"broken\n",
        b'{"version":1,"version":1,"id":"x","command":"hello","payload":{}}\n',
        b'{"version":9,"id":"x","command":"hello","payload":{}}\n',
        b'{"version":1,"id":"x","command":"hello","payload":{"extra":1}}\n',
        b"x" * (1024 * 1024 + 1),
    ):
        result = json.loads(bridge.process_line(line))
        assert not result["ok"]
        assert set(result) == {"version", "id", "ok", "error"}
    assert call(bridge, "hello", {})["result"] == {"protocol": 1}


@pytest.mark.parametrize(
    "message,code",
    [
        ("Source keys must be non-empty and safe text.", "source_key_invalid"),
        (
            "Policy schema or safety constraints are invalid; see policy-format.md.",
            "policy_configuration",
        ),
        ("Added analysis worksheet contains unsafe content.", "analysis_sheet"),
        ("Original source does not match the restoration bundle.", "source_mismatch"),
        ("A protected source field was changed.", "protected_value"),
        ("Returned record coverage does not match the bundle.", "record_coverage"),
        ("Restoration bundle could not be authenticated or decoded.", "bundle_authentication"),
        ("private synthetic value must never cross", "safety_rejected"),
    ],
)
def test_bridge_returns_only_allowlisted_value_free_safety_codes(message, code):
    class RejectingBridge(Bridge):
        def dispatch(self, command: str, raw: object) -> dict:
            raise SafetyError(message)

    result = call(RejectingBridge(), "hello", {})
    assert result["error"] == code
    assert message not in json.dumps(result)


def test_bridge_category_review_reports_blank_count_without_blank_values(tmp_path):
    source = tmp_path / "synthetic-blanks.xlsx"
    source.write_bytes(
        excel_bytes(
            Table(
                ("synthetic_key", "category"),
                (
                    {"synthetic_key": "SYNTH-001", "category": "Alpha"},
                    {"synthetic_key": "SYNTH-002", "category": ""},
                ),
            )
        )
    )
    result = call(
        Bridge(),
        "categories",
        {"source": str(source), "sheet": None, "column": "category"},
    )
    assert result["ok"]
    assert result["result"] == {"values": ["Alpha"], "blank_count": 1}


def test_bridge_round_trip_and_review_invalidation(destinations, monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("Network access attempted")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    bridge = Bridge()
    source = ROOT / "examples/synthetic_students.xlsx"
    output, bundle = destinations
    drafts, threshold = draft_payload()
    request = {
        "source": str(source),
        "sheet": None,
        "output": str(output),
        "bundle": str(bundle),
        "drafts": drafts,
        "threshold": threshold,
    }
    prepared = call(bridge, "prepare_protection", request)
    assert prepared["ok"] and prepared["result"]["validation"]["passed"]
    token = prepared["result"]["review_id"]
    assert not json.loads(bridge.process_line(b"broken\n"))["ok"]
    assert not call(bridge, "approve_protection", {"review_id": token, "passphrase": PASSPHRASE})[
        "ok"
    ]
    prepared = call(bridge, "prepare_protection", request)
    token = prepared["result"]["review_id"]
    assert call(bridge, "cancel", {})["result"] == {"cancelled": True}
    assert not call(bridge, "approve_protection", {"review_id": token, "passphrase": PASSPHRASE})[
        "ok"
    ]
    prepared = call(bridge, "prepare_protection", request)
    token = prepared["result"]["review_id"]
    call(bridge, "inspect", {"source": str(source), "sheet": None})
    stale = call(bridge, "approve_protection", {"review_id": token, "passphrase": PASSPHRASE})
    assert not stale["ok"] and not output.exists()
    prepared = call(bridge, "prepare_protection", request)
    token = prepared["result"]["review_id"]
    approved = call(
        bridge,
        "approve_protection",
        {
            "review_id": token,
            "passphrase": PASSPHRASE,
        },
    )
    assert approved["ok"] and output.exists() and bundle.exists()
    assert not call(
        bridge,
        "approve_protection",
        {
            "review_id": token,
            "passphrase": PASSPHRASE,
        },
    )["ok"]
    for row in read_excel(source).rows:
        assert row["student_name"] not in json.dumps(prepared)
        assert row["student_number"] not in json.dumps(prepared)
        assert row["student_number"] not in json.dumps(approved)
    table = read_excel(output)
    returned = output.parent / "returned.xlsx"
    returned.write_bytes(
        excel_bytes(
            Table(
                (*table.columns, "Team"),
                tuple({**row, "Team": "Robot Team"} for row in table.rows),
            )
        )
    )
    destination = output.parent.parent / "private/reconstructed.xlsx"
    reconstruction = {
        "returned": str(returned),
        "source": str(source),
        "bundle": str(bundle),
        "output": str(destination),
        "passphrase": PASSPHRASE,
        "returned_sheet": None,
        "source_sheet": None,
    }
    alternate_rows = [dict(row) for row in read_excel(source).rows]
    alternate_rows[0]["student_number"] = "SYNTH-CHANGED"
    alternate_source = output.parent / "other-source.xlsx"
    alternate_source.write_bytes(
        excel_bytes(Table(read_excel(source).columns, tuple(alternate_rows)))
    )
    assert not call(
        bridge, "prepare_reconstruction", {**reconstruction, "source": str(alternate_source)}
    )["ok"]
    wrong_bundle = bundle.parent / "wrong.enc"
    wrong_bundle.write_bytes(bundle.read_bytes()[:-1] + b"!")
    assert not call(
        bridge, "prepare_reconstruction", {**reconstruction, "bundle": str(wrong_bundle)}
    )["ok"]
    assert not call(
        bridge, "prepare_reconstruction", {**reconstruction, "passphrase": "incorrect-test-secret"}
    )["ok"]
    review = call(bridge, "prepare_reconstruction", reconstruction)
    assert review["ok"] and review["result"]["new_columns"] == ["Team"]
    assert PASSPHRASE not in json.dumps(review)
    token = review["result"]["review_id"]
    assert not call(
        bridge,
        "approve_reconstruction",
        {
            "review_id": token,
            "approved_results": [],
        },
    )["ok"]
    assert not destination.exists()
    review = call(bridge, "prepare_reconstruction", reconstruction)
    result = call(
        bridge,
        "approve_reconstruction",
        {
            "review_id": review["result"]["review_id"],
            "approved_results": ["Team"],
        },
    )
    assert result["ok"] and read_excel(destination).rows[0]["Team"] == "Robot Team"
    again = call(
        bridge,
        "prepare_reconstruction",
        {
            **reconstruction,
            "output": str(destination),
        },
    )
    assert not again["ok"]

    selected_review = call(
        bridge,
        "prepare_reconstruction",
        {
            **reconstruction,
            "output": str(output.parent.parent / "private/selected-reconstructed.xlsx"),
            "returned_sheet": list(list_excel_sheets(returned)),
            "source_sheet": list(list_excel_sheets(source)),
        },
    )
    assert selected_review["ok"]

    repeated = call(
        Bridge(),
        "prepare_reconstruction",
        {
            **reconstruction,
            "output": str(output.parent.parent / "private/repeated-reconstructed.xlsx"),
            "returned_sheet": [
                list_excel_sheets(returned)[0],
                list_excel_sheets(returned)[0],
            ],
            "source_sheet": list(list_excel_sheets(source)),
        },
    )
    assert not repeated["ok"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "field"])
def test_bridge_rejects_changed_returned_workbook(destinations, change):
    bridge = Bridge()
    source = ROOT / "examples/synthetic_students.xlsx"
    output, bundle = destinations
    drafts, threshold = draft_payload()
    prepare = call(
        bridge,
        "prepare_protection",
        {
            "source": str(source),
            "sheet": None,
            "output": str(output),
            "bundle": str(bundle),
            "drafts": drafts,
            "threshold": threshold,
        },
    )
    assert call(
        bridge,
        "approve_protection",
        {
            "review_id": prepare["result"]["review_id"],
            "passphrase": PASSPHRASE,
        },
    )["ok"]
    original = read_excel(output)
    rows = [dict(row) for row in original.rows]
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows[0]["record_id"] = rows[1]["record_id"]
    elif change == "unknown":
        from safeset.pseudonyms import new_id

        rows[0]["record_id"] = new_id()
    else:
        rows[0]["campus"] = "changed"
    returned = output.parent / "changed.xlsx"
    returned.write_bytes(excel_bytes(Table(original.columns, tuple(rows))))
    result = call(
        bridge,
        "prepare_reconstruction",
        {
            "returned": str(returned),
            "source": str(source),
            "bundle": str(bundle),
            "output": str(output.parent.parent / "private/restored.xlsx"),
            "passphrase": PASSPHRASE,
            "returned_sheet": None,
            "source_sheet": None,
        },
    )
    assert not result["ok"]
    assert result["error"] == {
        "missing": "record_coverage",
        "duplicate": "record_ids",
        "unknown": "record_coverage",
        "field": "protected_value",
    }[change]
