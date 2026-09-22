from copy import deepcopy

import pytest
import yaml
from openpyxl import Workbook

from safeset.errors import SafetyError
from safeset.ingestion import MAX_FIELD, Table, excel_bytes, read_bounded, read_excel
from safeset.policy import load_policy, parse_policy
from safeset.transform import sanitise

from .conftest import ROOT


@pytest.mark.parametrize(
    "change",
    [
        lambda w: setattr(w.active["A1"], "value", "b"),
        lambda w: setattr(w.active["A1"], "value", " a"),
        lambda w: setattr(w.active["A2"], "value", "=" + "1+2"),
        lambda w: setattr(w.active["A2"], "value", "x" * (MAX_FIELD + 1)),
        lambda w: setattr(w.active.row_dimensions[2], "hidden", True),
        lambda w: w.active.merge_cells("A1:B1"),
        lambda w: w.create_sheet("Extra"),
        lambda w: setattr(w.active["A2"], "hyperlink", "https://example.invalid"),
    ],
)
def test_malformed_excel_rejected(change, tmp_path):
    workbook = Workbook()
    workbook.active.append(("a", "b"))
    workbook.active.append(("safe", "value"))
    change(workbook)
    path = tmp_path / "bad.xlsx"
    workbook.save(path)
    with pytest.raises(SafetyError):
        read_excel(path)


def test_non_utf8_and_size_bounds(tmp_path):
    path = tmp_path / "bad.xlsx"
    path.write_bytes(b"\xff")
    with pytest.raises(SafetyError):
        read_excel(path)
    path.write_bytes(b"x" * 21)
    with pytest.raises(SafetyError):
        read_bounded(path, 20)


def test_excel_only_and_literal_text_round_trip(tmp_path):
    path = tmp_path / "literal.xlsx"
    path.write_bytes(excel_bytes(Table(("key", "value"), ({"key": "000123", "value": "=1+2"},))))
    assert read_excel(path).rows == ({"key": "000123", "value": "=1+2"},)
    with pytest.raises(SafetyError, match="Only .xlsx"):
        read_excel(tmp_path / "old.csv")


@pytest.mark.parametrize(
    "text",
    [
        "version: 1\nversion: 1\n",
        "a: &a [*a]",
        "x: !!python/object:thing {}",
        "version: true\ncolumns: {}\nmin_group_size: 2",
        "- a\n- b",
        "version: 3\ncolumns: {}\nmin_group_size: 2",
    ],
)
def test_hostile_or_invalid_yaml(text, tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(text)
    with pytest.raises(SafetyError):
        load_policy(path)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(unexpected=True),
        lambda p: p.update(min_group_size=1),
        lambda p: p.update(min_group_size=True),
        lambda p: p["columns"]["campus"].update(classification="unknown"),
        lambda p: p["columns"]["campus"].update(classification="free_text"),
        lambda p: p["columns"]["campus"].update(action="redact"),
        lambda p: p["columns"]["campus"].update(allowed_values=["x@example.invalid"]),
        lambda p: p["columns"]["campus"].update(allowed_values=["2020-01-01"]),
        lambda p: p["columns"]["campus"].update(allowed_values=["12345678"]),
        lambda p: p["columns"]["campus"].update(allowed_values=["=SUM(1,2)"]),
        lambda p: p["columns"]["campus"].update(
            allowed_values=["this is deliberately long personal prose"]
        ),
        lambda p: p["columns"]["campus"].update(allowed_values=[True]),
        lambda p: p["columns"]["campus"].update(allowed_values=["Moon", "Moon"]),
        lambda p: p["columns"]["gpa"].update(bounds=[0, 0]),
        lambda p: p["columns"]["gpa"].update(bounds=[0, float("inf")]),
        lambda p: p["columns"]["gpa"].update(bounds=[-1, 7]),
        lambda p: p["columns"]["gpa"].update(bounds=[True, 7]),
        lambda p: p["columns"]["gpa"].update(max_decimal_places=True),
        lambda p: p["columns"]["gpa"].update(max_decimal_places=7),
        lambda p: p["columns"]["gpa"].update(bins=[[0, 7]]),
        lambda p: p["columns"]["campus"].update(bins=[[0, 7]]),
        lambda p: p["columns"]["student_number"].update(action="drop"),
        lambda p: p["columns"]["email"].update(action="pseudonymise"),
        lambda p: p["columns"].update(record_id={"action": "drop", "classification": "unknown"}),
        lambda p: p["columns"]["notes"].update(
            action="keep", classification="analytical_attribute", allowed_values=["ok"]
        ),
        lambda p: p["columns"]["email"].update(
            action="keep", classification="analytical_attribute", allowed_values=["ok"]
        ),
    ],
)
def test_policy_fail_closed(change):
    raw = yaml.safe_load((ROOT / "examples/example-policy.yaml").read_text())
    change(raw)
    with pytest.raises(SafetyError):
        parse_policy(raw)


@pytest.mark.parametrize(
    "value",
    ["", "NaN", "Infinity", "-1", "7.1", "secret-nonnumeric", "4.123", "4e0", "+4.2"],
)
def test_invalid_numeric_values_do_not_leak(source, policy, value):
    rows = deepcopy(source.rows)
    rows[0]["gpa"] = value
    with pytest.raises(SafetyError) as caught:
        sanitise(Table(source.columns, rows), policy)
    if value:
        assert value not in str(caught.value)


def test_numeric_value_is_preserved_without_formatting(source, policy):
    rows = tuple({**row, "gpa": "04.20"} for row in source.rows)
    candidate = sanitise(Table(source.columns, rows), policy)
    assert [row["gpa"] for row in candidate.table.rows] == ["4.2"] * len(rows)


def test_unapproved_category_does_not_leak(source, policy):
    rows = deepcopy(source.rows)
    rows[0]["campus"] = "Secret synthetic campus"
    with pytest.raises(SafetyError) as caught:
        sanitise(Table(source.columns, rows), policy)
    assert "Secret synthetic campus" not in str(caught.value)


@pytest.mark.parametrize(
    "value,label",
    [("0", "[0, 4)"), ("4", "[4, 5)"), ("5", "[5, 6)"), ("6", "[6, 7]"), ("7", "[6, 7]")],
)
def test_v1_bin_boundaries(source, value, label):
    raw = yaml.safe_load((ROOT / "examples/example-policy.yaml").read_text())
    raw["version"] = 1
    raw["columns"]["campus"]["action"] = "keep"
    raw["columns"]["subject"]["action"] = "keep"
    raw["columns"]["gpa"] = {
        "action": "bin",
        "classification": "quasi_identifier",
        "bins": [[0, 4], [4, 5], [5, 6], [6, 7]],
    }
    policy = parse_policy(raw)
    rows = tuple({**r, "gpa": value} for r in source.rows)
    assert sanitise(Table(source.columns, rows), policy).table.rows[0]["gpa"] == label


def test_v1_rejects_new_actions():
    raw = yaml.safe_load((ROOT / "examples/example-policy.yaml").read_text())
    raw["version"] = 1
    with pytest.raises(SafetyError):
        parse_policy(raw)


@pytest.mark.parametrize("mode", ["extra", "missing", "duplicate_key", "empty_key", "empty"])
def test_source_schema_and_keys(source, policy, mode):
    rows = deepcopy(source.rows)
    columns = source.columns
    if mode == "extra":
        columns = (*columns, "new_sensitive_field")
        rows = tuple({**r, "new_sensitive_field": "invented"} for r in rows)
    elif mode == "missing":
        columns = columns[:-1]
    elif mode == "duplicate_key":
        rows[0]["student_number"] = rows[1]["student_number"]
    elif mode == "empty_key":
        rows[0]["student_number"] = ""
    else:
        rows = ()
    with pytest.raises(SafetyError):
        sanitise(Table(columns, rows), policy)


def test_fifo_rejected_without_blocking(tmp_path):
    import os

    path = tmp_path / "pipe"
    os.mkfifo(path)
    with pytest.raises(SafetyError, match="regular"):
        read_bounded(path)


@pytest.mark.parametrize("value", ["=1+2", "+1234", "@command", "bad\tkey"])
def test_source_keys_must_be_restorable(source, policy, value):
    rows = tuple(
        {**r, "student_number": value if i == 0 else r["student_number"]}
        for i, r in enumerate(source.rows)
    )
    with pytest.raises(SafetyError):
        sanitise(Table(source.columns, rows), policy)
