"""Visibly synthetic narrative review, protection and restoration regressions."""

import json
import socket

import pytest
import yaml

from safeset.bundle import create_bundle, decrypt_bundle, encrypt_bundle
from safeset.classification import inferred_classification
from safeset.desktop_bridge import Bridge
from safeset.errors import SafetyError
from safeset.ingestion import MAX_FIELD, Table, excel_bytes, excel_workbook_bytes, read_excel
from safeset.policy import load_policy, parse_policy
from safeset.policy_authoring import RuleDraft, load_drafts, policy_payload
from safeset.reconstruction import reconstruct
from safeset.relational import (
    create_relational_bundle,
    decrypt_relational_bundle,
    encrypt_relational_bundle,
    reconstruct_relational,
    sanitise_relational,
    validate_relational,
)
from safeset.text_review import (
    TextReviewRejection,
    approve_text_reviews,
    review_entries,
    text_digest,
)
from safeset.transform import sanitise
from safeset.validation import validate
from safeset.workbook_editing import validate_editable_fields
from safeset.workflow import export_candidate

from .conftest import PASSPHRASE

ORIGINAL = (
    "Synthetic Ada discussed a wholly invented learning exercise in the imaginary laboratory.\n"
    "Contact synthetic.ada@example.invalid for the fictional follow-up."
)
REVIEWED = (
    "A participant discussed a wholly invented learning exercise.\r\n"
    "The response described how the exercise improved their understanding and reflection."
)


def fixture():
    source = Table(
        ("Synthetic key", "Student Name", "Journal response"),
        tuple(
            {
                "Synthetic key": f"SYNTH-{index:03}",
                "Student Name": "Synthetic Ada",
                "Journal response": ORIGINAL,
            }
            for index in range(2)
        ),
    )
    raw = {
        "version": 4,
        "min_group_size": 2,
        "columns": {
            "Synthetic key": {"action": "pseudonymise", "classification": "direct_identifier"},
            "Student Name": {"action": "drop", "classification": "direct_identifier"},
            "Journal response": {
                "action": "review_text",
                "classification": "free_text",
                "text_reviews": {text_digest(ORIGINAL): REVIEWED},
            },
        },
    }
    return source, raw


def call(bridge, command, payload):
    return json.loads(
        bridge.process_line(
            json.dumps(
                {
                    "version": 1,
                    "id": "synthetic-text-review",
                    "command": command,
                    "payload": payload,
                }
            ).encode()
            + b"\n"
        )
    )


@pytest.mark.parametrize("version", [1, 2, 3])
def test_older_policies_cannot_reinterpret_reviewed_text(version):
    _, raw = fixture()
    raw["version"] = version
    with pytest.raises(SafetyError):
        parse_policy(raw)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(text_reviews={}),
        lambda r: r.update(text_reviews={"not-a-digest": REVIEWED}),
        lambda r: r.update(text_reviews={text_digest(ORIGINAL): True}),
        lambda r: r.update(text_reviews={text_digest(ORIGINAL): "x" * (MAX_FIELD + 1)}),
        lambda r: r.update(text_reviews={text_digest(ORIGINAL): " \t "}),
        lambda r: r.update(text_reviews={text_digest(ORIGINAL): "=synthetic formula"}),
        lambda r: r.update(text_reviews={text_digest(ORIGINAL): "synthetic@example.invalid"}),
        lambda r: r.update(text_reviews={text_digest(ORIGINAL): "Call 0412345678"}),
        lambda r: r.update(text_reviews={text_digest(ORIGINAL): "Met on 2026-01-01"}),
        lambda r: r.update(text_reviews={text_digest(ORIGINAL): "At 14:30"}),
        lambda r: r.update(text_reviews={text_digest(ORIGINAL): "Unsafe\x7ftext"}),
        lambda r: r.update(classification="analytical_attribute"),
        lambda r: r.update(unknown_option=True),
    ],
)
def test_review_text_schema_fails_closed(change):
    _, raw = fixture()
    change(raw["columns"]["Journal response"])
    with pytest.raises(SafetyError):
        parse_policy(raw)


def test_text_review_does_not_relax_categories_or_identifier_headings():
    _, raw = fixture()
    raw["columns"]["Journal response"] = {
        "action": "keep",
        "classification": "analytical_attribute",
        "allowed_values": [REVIEWED],
    }
    with pytest.raises(SafetyError):
        parse_policy(raw)


@pytest.mark.parametrize(
    "heading",
    [
        "How could you address the research challenges in this fictional project?",
        "What training would help you address your learning needs?",
        "Describe ways to address development needs.",
    ],
)
def test_narrative_address_verb_is_not_an_identifier_source(heading):
    source, raw = fixture()
    text = "A wholly invented response about requesting training and laboratory support."
    rows = tuple({**row, heading: text} for row in source.rows)
    rows = tuple(
        {name: value for name, value in row.items() if name != "Journal response"} for row in rows
    )
    source = Table(("Synthetic key", "Student Name", heading), rows)
    raw["columns"][heading] = raw["columns"].pop("Journal response")
    raw["columns"][heading]["text_reviews"] = {text_digest(text): text}
    assert inferred_classification(heading) == "free_text"
    approve_text_reviews(source, heading, {text_digest(text): text})
    policy = parse_policy(raw)
    candidate = sanitise(source, policy)
    assert validate(candidate.table, policy).passed
    bundle = create_bundle(source, policy, candidate)
    assert reconstruct(source, candidate.table, bundle, ()) == source


@pytest.mark.parametrize(
    "heading",
    [
        "Address",
        "Postal address",
        "Email address",
        "What is your address?",
        "Student Name",
        "How could you address your learning needs? Email address",
    ],
)
def test_actual_identifier_headings_remain_blocked_for_narrative_review(heading):
    assert inferred_classification(heading) == "direct_identifier"
    source = Table((heading,), ({heading: "Synthetic identifier"},))
    with pytest.raises(TextReviewRejection) as caught:
        approve_text_reviews(source, heading, {text_digest("Synthetic identifier"): "A paragraph."})
    assert caught.value.issues == {"": ["identifier_field"]}
    _, raw = fixture()
    raw["columns"][heading] = raw["columns"].pop("Journal response")
    with pytest.raises(SafetyError):
        parse_policy(raw)


def test_complete_review_and_known_source_identifiers_are_enforced():
    source, raw = fixture()
    for text in ("Synthetic Ada worked on an exercise.", "Participant SYNTH-000 reflected."):
        raw["columns"]["Journal response"]["text_reviews"] = {text_digest(ORIGINAL): text}
        with pytest.raises(SafetyError, match="Long-form text") as caught:
            sanitise(source, parse_policy(raw))
        assert text not in str(caught.value)
    source, raw = fixture()
    policy = parse_policy(raw)
    changed = Table(
        source.columns,
        tuple({**r, "Journal response": ORIGINAL + " Changed."} for r in source.rows),
    )
    with pytest.raises(SafetyError, match="Long-form text"):
        sanitise(changed, policy)
    raw["columns"]["Journal response"]["text_reviews"][text_digest("Unobserved text")] = REVIEWED
    with pytest.raises(SafetyError, match="Long-form text"):
        sanitise(source, parse_policy(raw))


@pytest.mark.parametrize(
    "text,reason",
    [
        ("Contact synthetic@example.invalid", "email"),
        ("An event on 2026-01-01", "date"),
        ("An event at 14:30", "time"),
        ("Phone 0412345678", "long_digits"),
        ("Synthetic Ada described a fictional exercise.", "known_identifier"),
        ("=An invented paragraph", "formula_prefix"),
        ("\t  ", "whitespace_only"),
        ("Synthetic\x7ftext", "control_character"),
        ("x" * (MAX_FIELD + 1), "too_long"),
    ],
)
def test_approval_reports_response_specific_fixed_reasons_without_values(tmp_path, text, reason):
    source, _ = fixture()
    path = tmp_path / "synthetic-narrative.xlsx"
    path.write_bytes(excel_workbook_bytes({"Synthetic": source}))
    response = call(
        Bridge(),
        "approve_text_review",
        {
            "source": str(path),
            "sheet": "Synthetic",
            "column": "Journal response",
            "text_reviews": {text_digest(ORIGINAL): text},
        },
    )
    assert not response["ok"] and response["error"] == "text_review_required"
    assert reason in response["issues"][text_digest(ORIGINAL)]
    encoded = json.dumps(response)
    assert ORIGINAL not in encoded and text not in encoded
    assert "Student Name" not in encoded and str(path) not in encoded
    log = (tmp_path / "diagnostics/safeset.log").read_text()
    assert text_digest(ORIGINAL) not in log and ORIGINAL not in log


def test_stale_review_feedback_is_global_and_never_returns_new_source_content():
    source, _ = fixture()
    with pytest.raises(TextReviewRejection) as caught:
        approve_text_reviews(source, "Journal response", {"b" * 64: REVIEWED})
    assert caught.value.issues == {"": ["source_changed"]}
    assert ORIGINAL not in str(caught.value)


def test_highlights_identify_every_repeated_match_using_utf16_offsets(tmp_path):
    source, _ = fixture()
    text = (
        "🧪 Synthetic Ada emailed synthetic@example.invalid, then synthetic@example.invalid. "
        "Synthetic Ada noted 2026-01-01 at 14:30; phone 0412345678."
    )
    path = tmp_path / "synthetic-highlight.xlsx"
    path.write_bytes(excel_workbook_bytes({"Synthetic": source}))
    response = call(
        Bridge(),
        "approve_text_review",
        {
            "source": str(path),
            "sheet": "Synthetic",
            "column": "Journal response",
            "text_reviews": {text_digest(ORIGINAL): text},
        },
    )
    assert not response["ok"]
    ranges = response["highlights"][text_digest(ORIGINAL)]
    matched = {}
    encoded = text.encode("utf-16-le")
    for mark in ranges:
        excerpt = encoded[2 * mark["start"] : 2 * mark["end"]].decode("utf-16-le")
        matched.setdefault(mark["reason"], []).append(excerpt)
    assert matched["known_identifier"] == ["Synthetic Ada", "Synthetic Ada"]
    assert matched["email"] == ["synthetic@example.invalid"] * 2
    assert matched["date"] == ["2026-01-01"]
    assert matched["time"] == ["14:30"]
    assert matched["long_digits"] == ["2026-01-01", "0412345678"]
    assert set(ranges[0]) == {"reason", "start", "end"}
    serialised = json.dumps(response)
    for secret in ("Synthetic Ada", "synthetic@example.invalid", text, str(path)):
        assert secret not in serialised
    log = (tmp_path / "diagnostics/safeset.log").read_text()
    assert text_digest(ORIGINAL) not in log and "highlights" not in log


def test_known_identifier_casefold_ranges_point_to_original_characters():
    source, _ = fixture()
    source = Table(
        source.columns, tuple({**row, "Student Name": "Synthetic Straße"} for row in source.rows)
    )
    text = "🧪 SYNTHETIC STRASSE reflected. Synthetic Straße also reflected."
    with pytest.raises(TextReviewRejection) as caught:
        approve_text_reviews(source, "Journal response", {text_digest(ORIGINAL): text})
    encoded = text.encode("utf-16-le")
    spans = caught.value.highlights[text_digest(ORIGINAL)]
    assert [
        encoded[2 * s["start"] : 2 * s["end"]].decode("utf-16-le")
        for s in spans
        if s["reason"] == "known_identifier"
    ] == ["SYNTHETIC STRASSE", "Synthetic Straße"]


def test_highlights_are_bounded_and_oversize_ranges_use_native_offsets():
    source, _ = fixture()
    text = "🧪" * (MAX_FIELD + 1)
    with pytest.raises(TextReviewRejection) as caught:
        approve_text_reviews(source, "Journal response", {text_digest(ORIGINAL): text})
    assert caught.value.highlights[text_digest(ORIGINAL)] == [
        {"reason": "too_long", "start": MAX_FIELD * 2, "end": (MAX_FIELD + 1) * 2}
    ]
    text = "synthetic@example.invalid " * 200
    with pytest.raises(TextReviewRejection) as caught:
        approve_text_reviews(source, "Journal response", {text_digest(ORIGINAL): text})
    assert len(caught.value.highlights[text_digest(ORIGINAL)]) <= 128


def test_reviewed_text_encrypted_round_trip_and_exact_output_binding(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("Network attempted"))
    source, raw = fixture()
    policy = parse_policy(raw)
    candidate = sanitise(source, policy)
    report = validate(candidate.table, policy)
    assert report.passed and report.minimum_class_size == 2
    assert any("narrative" in warning for warning in report.warnings)
    assert ORIGINAL not in json.dumps(candidate.mapping)
    assert REVIEWED not in json.dumps(candidate.mapping)
    protected = tmp_path / "synthetic-protected.xlsx"
    protected.write_bytes(excel_bytes(candidate.table))
    assert read_excel(protected) == candidate.table
    assert ORIGINAL not in str(read_excel(protected).rows)
    bundle = decrypt_bundle(
        encrypt_bundle(create_bundle(source, policy, candidate), PASSPHRASE), PASSPHRASE
    )
    assert reconstruct(source, read_excel(protected), bundle, ()) == source
    changed = Table(
        candidate.table.columns,
        tuple({**r, "Journal response": "Changed text"} for r in candidate.table.rows),
    )
    with pytest.raises(SafetyError, match="protected source field"):
        reconstruct(source, changed, bundle, ())
    assert not validate(changed, policy).passed


def test_unique_reviewed_responses_still_enter_disclosure_groups():
    source, raw = fixture()
    original = ORIGINAL + " Another invented response."
    source = Table(
        source.columns, (source.rows[0], {**source.rows[1], "Journal response": original})
    )
    raw["columns"]["Journal response"]["text_reviews"][text_digest(original)] = (
        REVIEWED + " Unique."
    )
    policy = parse_policy(raw)
    candidate = sanitise(source, policy)
    strict = validate(candidate.table, policy)
    assert not strict.passed and strict.minimum_class_size == 1
    controlled = validate(candidate.table, policy, "controlled_pseudonymisation")
    assert controlled.passed and controlled.small_class_records == 2
    assert any("Small joint" in warning for warning in controlled.warnings)


def test_narrative_is_reference_only_and_linked_checks_remain_active(tmp_path):
    source, raw = fixture()
    policy = parse_policy(raw)
    sources, policies = {"Synthetic": source}, {"Synthetic": policy}
    candidate = sanitise_relational(sources, policies)
    report = validate_relational(candidate, policies)
    assert report.passed and report.minimum_linked_group_size == 2
    bundle = create_relational_bundle(sources, policies, candidate, "strict")
    bundle = decrypt_relational_bundle(encrypt_relational_bundle(bundle, PASSPHRASE), PASSPHRASE)
    assert reconstruct_relational(sources, candidate.tables, bundle, {"Synthetic": ()}) == sources
    with pytest.raises(SafetyError):
        validate_editable_fields({"Synthetic": ["Journal response"]}, policies)
    path = tmp_path / "synthetic-multiple-sheets.xlsx"
    path.write_bytes(excel_workbook_bytes(candidate.tables))
    assert read_excel(path) == candidate.tables["Synthetic"]


@pytest.mark.parametrize("region", [False, True])
def test_explicit_local_review_protocol_and_value_free_logs(tmp_path, region):
    source, raw = fixture()
    path = tmp_path / "synthetic-narrative.xlsx"
    path.write_bytes(excel_workbook_bytes({"Synthetic": source}))
    bridge = Bridge()
    payload = {"source": str(path), "column": "Journal response"}
    if region:
        payload.update(name="Synthetic region", region={"sheet": "Synthetic", "range": "A1:C3"})
    else:
        payload["sheet"] = "Synthetic"
    command = "region_text_review" if region else "text_review"
    result = call(bridge, command, payload)
    assert result["ok"]
    assert result["result"]["entries"] == [
        {"digest": text_digest(ORIGINAL), "original": ORIGINAL, "count": 2},
    ]
    approval = "approve_region_text_review" if region else "approve_text_review"
    approved = call(
        bridge,
        approval,
        {
            **payload,
            "text_reviews": raw["columns"]["Journal response"]["text_reviews"],
        },
    )
    assert approved["ok"]
    invalid = call(bridge, approval, {**payload, "text_reviews": {text_digest(ORIGINAL): ORIGINAL}})
    assert invalid["error"] == "text_review_required"
    inspected = call(bridge, "inspect", {"source": str(path), "sheet": "Synthetic"})
    assert ORIGINAL not in json.dumps(inspected)
    log = (tmp_path / "diagnostics/safeset.log").read_text()
    for secret in (
        ORIGINAL,
        REVIEWED,
        "Student Name",
        "synthetic-narrative.xlsx",
        text_digest(ORIGINAL),
    ):
        assert secret not in log


def test_review_bounds_blank_response_and_yaml_round_trip(tmp_path):
    source, raw = fixture()
    raw["columns"]["Journal response"]["text_reviews"] = {text_digest(ORIGINAL): ""}
    policy = parse_policy(raw)
    assert validate(sanitise(source, policy).table, policy).passed
    assert review_entries(source, "Journal response")[0]["count"] == 2
    with pytest.raises(SafetyError):
        review_entries(Table(("text",), tuple({"text": str(i)} for i in range(1001))), "text")
    with pytest.raises(SafetyError):
        approve_text_reviews(source, "Journal response", {})
    path = tmp_path / "synthetic-source.xlsx"
    path.write_bytes(excel_bytes(source))
    policy_path = tmp_path / "synthetic-policy.yaml"
    policy_path.write_text(yaml.safe_dump(raw))
    assert load_policy(policy_path) == policy
    drafts, threshold = load_drafts(path, policy_path)
    assert parse_policy(policy_payload(drafts, str(threshold))) == policy
    drafts["Journal response"] = RuleDraft("review_text")
    with pytest.raises(SafetyError):
        policy_payload(drafts, "2")
    duplicate = yaml.safe_dump(raw).replace(
        "text_reviews:", "text_reviews: {}\n    text_reviews:", 1
    )
    policy_path.write_text(duplicate)
    with pytest.raises(SafetyError):
        load_policy(policy_path)


@pytest.mark.parametrize("region", [False, True])
def test_desktop_reviewed_text_editable_bundle_round_trip(tmp_path, monkeypatch, region):
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("Network attempted"))
    source, raw = fixture()
    path = tmp_path / "synthetic-narrative.xlsx"
    path.write_bytes(excel_workbook_bytes({"Synthetic": source}))
    for name in ("exports", "maps", "private"):
        (tmp_path / name).mkdir(mode=0o700)
    output = tmp_path / "exports/protected.xlsx"
    bundle_path = tmp_path / "maps/bundle.enc"
    restored = tmp_path / "private/restored.xlsx"
    bridge = Bridge()
    sheet = "Region" if region else "Synthetic"
    drafts = {
        name: {
            "action": rule["action"],
            "classification": rule["classification"],
            "allowed_values": [],
            "bins": [],
            "bounds": None,
            **({"text_reviews": rule["text_reviews"]} if rule["action"] == "review_text" else {}),
        }
        for name, rule in raw["columns"].items()
    }
    request = {
        "source": str(path),
        "sheets": [sheet],
        "drafts": {sheet: drafts},
        "threshold": "2",
        "output": str(output),
        "bundle": str(bundle_path),
        "validation_profile": "strict",
        "editable_fields": {sheet: []},
    }
    if region:
        discovery = call(bridge, "discover_regions", {"path": str(path)})["result"]
        request.update(
            regions={sheet: {"sheet": "Synthetic", "range": "A1:C3"}},
            region_digest=discovery["source_digest"],
        )
    review = call(bridge, "prepare_relational_protection", request)
    assert review["ok"] and review["result"]["validation"]["passed"]
    assert not output.exists() and not bundle_path.exists()
    assert ORIGINAL not in json.dumps(review) and REVIEWED not in json.dumps(review)
    assert call(
        bridge,
        "approve_relational_protection",
        {
            "review_id": review["result"]["review_id"],
            "passphrase": PASSPHRASE,
        },
    )["ok"]
    assert read_excel(output).rows[0]["Journal response"] == REVIEWED
    restore_review = call(
        bridge,
        "prepare_relational_reconstruction",
        {
            "source": str(path),
            "returned": str(output),
            "bundle": str(bundle_path),
            "output": str(restored),
            "passphrase": PASSPHRASE,
        },
    )
    assert restore_review["ok"]
    assert not restored.exists()
    assert call(
        bridge,
        "approve_relational_reconstruction",
        {
            "review_id": restore_review["result"]["review_id"],
            "approved_results": {sheet: []},
            "approved_changes": {sheet: []},
        },
    )["ok"]
    assert read_excel(restored) == source
    log = (tmp_path / "diagnostics/safeset.log").read_text()
    assert ORIGINAL not in log and REVIEWED not in log and PASSPHRASE not in log


def test_legacy_map_export_cannot_publish_unrestorable_narrative(tmp_path):
    source, raw = fixture()
    policy = parse_policy(raw)
    candidate = sanitise(source, policy)
    output = tmp_path / "never-created.xlsx"
    with pytest.raises(SafetyError, match="requires a restoration bundle"):
        export_candidate(
            candidate,
            policy,
            output,
            tmp_path / "map.enc",
            PASSPHRASE,
            approved=True,
            create_map=True,
            source_path=tmp_path / "source.xlsx",
        )
    assert not output.exists()
