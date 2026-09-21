import json
import socket
import stat

import pytest
from typer.testing import CliRunner

from safeset.cli import app
from safeset.ingestion import Table, csv_bytes, read_csv
from safeset.mapping import read_mapping
from safeset.pseudonyms import valid_id
from safeset.restoration import restore
from safeset.transform import sanitise
from safeset.validation import validate
from safeset.workflow import export_candidate

from .conftest import PASSPHRASE, ROOT


def test_round_trip_without_network(source, policy, destinations, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Runtime attempted network access")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    first = sanitise(source, policy)
    second = sanitise(source, policy)
    assert set(first.mapping["records"]).isdisjoint(second.mapping["records"])
    for name in ("campus", "subject"):
        first_codes = [row[name] for row in first.table.rows]
        second_codes = [row[name] for row in second.table.rows]
        assert all(valid_id(code) for code in first_codes)
        assert set(first_codes).isdisjoint(second_codes)
        for left in range(len(source.rows)):
            for right in range(len(source.rows)):
                assert (first_codes[left] == first_codes[right]) == (
                    source.rows[left][name] == source.rows[right][name]
                )
    assert [row["gpa"] for row in first.table.rows] == [row["gpa"] for row in source.rows]
    assert validate(first.table, policy).passed
    output, map_path = destinations
    export_candidate(
        first,
        policy,
        output,
        map_path,
        PASSPHRASE,
        approved=True,
        create_map=True,
        source_path=ROOT / "examples/synthetic_students.csv",
    )
    exported = output.read_text()
    for row in source.rows:
        for field in ["student_name", "student_number", "email", "notes", "campus", "subject"]:
            assert row[field] not in exported
            assert row[field].encode() not in map_path.read_bytes()
    assert "student_number" not in exported
    assert stat.S_IMODE(map_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    mapping = read_mapping(map_path, PASSPHRASE)
    assert set(mapping) == {"version", "source_column", "records"}
    assert set(mapping["records"].values()) == {r["student_number"] for r in source.rows}
    ids = [r["record_id"] for r in read_csv(output).rows]
    analysed = Table(
        ("record_id", "team"), tuple({"record_id": v, "team": "RobotTeam"} for v in reversed(ids))
    )
    restored = restore(analysed, mapping, ("team",))
    assert [r["student_number"] for r in restored.rows] == [
        r["student_number"] for r in reversed(source.rows)
    ]
    assert restored.columns == ("student_number", "team")
    assert restore(analysed, mapping, ("team",)) == restored


def test_cli_round_trip_and_no_value_logging(destinations, monkeypatch):
    monkeypatch.setattr("safeset.cli.secret", lambda **kwargs: PASSPHRASE)
    runner = CliRunner()
    output, map_path = destinations
    source_path = ROOT / "examples/synthetic_students.csv"
    policy_path = ROOT / "examples/example-policy.yaml"
    args = [
        "sanitise",
        str(source_path),
        "--policy",
        str(policy_path),
        "--output",
        str(output),
        "--create-map",
        "--map",
        str(map_path),
        "--approve-export",
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "Passing checks does not establish anonymity" in result.output
    assert (
        runner.invoke(app, ["validate", str(output), "--policy", str(policy_path)]).exit_code == 0
    )
    inspected = runner.invoke(app, ["inspect", str(source_path)])
    assert inspected.exit_code == 0
    assert json.loads(inspected.output)["rows"] == 4
    restored_path = output.parent.parent / "private/restored.csv"
    result2 = runner.invoke(
        app,
        [
            "restore",
            str(output),
            "--map",
            str(map_path),
            "--output",
            str(restored_path),
            "--authorise",
            "--result-column",
            "campus",
            "--result-column",
            "subject",
            "--result-column",
            "gpa",
        ],
    )
    assert result2.exit_code == 0, result2.output
    assert read_csv(restored_path).rows[0]["student_number"] == "SYNTH-001"
    for row in read_csv(source_path).rows:
        for field in ["student_name", "student_number", "email", "notes", "campus", "subject"]:
            assert row[field] not in result.output + result2.output + inspected.output
    assert PASSPHRASE not in result.output + result2.output


@pytest.mark.parametrize("approval,create_map", [(False, True), (True, False)])
def test_service_requires_explicit_authorisation(
    candidate, policy, destinations, approval, create_map
):
    from safeset.errors import SafetyError

    output, map_path = destinations
    with pytest.raises(SafetyError):
        export_candidate(
            candidate,
            policy,
            output,
            map_path,
            PASSPHRASE,
            approved=approval,
            create_map=create_map,
            source_path=ROOT / "examples/synthetic_students.csv",
        )
    assert not output.exists() and not map_path.exists()


def test_leading_zero_source_keys_preserved(source, policy):
    rows = tuple({**r, "student_number": f"{i:06}"} for i, r in enumerate(source.rows))
    candidate = sanitise(Table(source.columns, rows), policy)
    restored = restore(candidate.table, candidate.mapping, ("campus", "subject", "gpa"))
    assert restored.rows[0]["student_number"] == "000000"
    assert b"000000" not in csv_bytes(candidate.table)
