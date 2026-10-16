import ast
import json
import stat

import pytest
from typer.testing import CliRunner

from safeset import diagnostics
from safeset.cli import app
from safeset.desktop_bridge import PUBLIC_SAFETY_ERRORS, Bridge
from safeset.diagnostics import record
from safeset.errors import SafetyError

from .conftest import ROOT


def desktop_call(bridge, command, payload):
    return json.loads(
        bridge.process_line(
            json.dumps(
                {
                    "version": 1,
                    "id": "secret-synthetic-request",
                    "command": command,
                    "payload": payload,
                }
            ).encode()
            + b"\n"
        )
    )


def test_desktop_logs_workbook_open_without_source_metadata():
    result = desktop_call(
        Bridge(),
        "list_sheets",
        {
            "path": str(ROOT / "examples/synthetic_students.xlsx"),
        },
    )
    assert result["ok"]
    content = diagnostics.log_path().read_text()
    assert "desktop.list_sheets start" in content
    assert "desktop.list_sheets success" in content
    for secret in (
        str(ROOT),
        "synthetic_students",
        "student_number",
        "SYNTH-001",
        "secret-synthetic-request",
    ):
        assert secret not in content


@pytest.mark.parametrize(
    "message,code",
    [
        ("Original source does not match the restoration bundle.", "source_mismatch"),
        ("secret-synthetic-exception", "safety_rejected"),
    ],
)
def test_desktop_logs_only_fixed_failure_codes(monkeypatch, message, code):
    def reject(*args):
        raise SafetyError(message)

    bridge = Bridge()
    monkeypatch.setattr(bridge, "dispatch", reject)
    response = desktop_call(
        bridge, "prepare_result_workbook", {"passphrase": "secret-synthetic-pass"}
    )
    assert response["error"] == code
    content = diagnostics.log_path().read_text()
    assert "desktop.prepare_result_workbook rejected" in content
    assert f"desktop.prepare_result_workbook {code}" in content
    assert "secret-synthetic" not in content


def test_desktop_unknown_commands_and_malformed_frames_are_value_free():
    bridge = Bridge()
    assert desktop_call(bridge, "secret-synthetic-command", {})["error"] == "invalid_request"
    assert not json.loads(bridge.process_line(b"secret-synthetic-frame\n"))["ok"]
    content = diagnostics.log_path().read_text()
    assert "desktop.protocol invalid_request" in content
    assert "secret-synthetic" not in content


def test_desktop_error_allowlist_covers_public_codes():
    assert set(PUBLIC_SAFETY_ERRORS.values()) <= diagnostics.DESKTOP_ERROR_CODES


def test_desktop_logging_failure_does_not_change_response(monkeypatch):
    monkeypatch.setattr("safeset.desktop_bridge.record", lambda *args: False)
    assert desktop_call(Bridge(), "hello", {})["ok"]


def test_private_log_contains_only_fixed_events():
    path = diagnostics.log_path()
    assert record("cli.inspect", "start")
    assert record("cli.inspect", "success")
    assert not record("cli.inspect", "secret-synthetic-value")
    assert not record("secret-synthetic-filename", "start")
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert lines[0].endswith(" cli.inspect start")
    assert lines[1].endswith(" cli.inspect success")
    assert "secret-synthetic" not in path.read_text()
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_only_allowlisted_reason_code_is_written():
    path = diagnostics.log_path()
    diagnostics.record_reason(
        "cli.inspect", SafetyError("Select one or more worksheets from the Excel workbook.")
    )
    diagnostics.record_reason("cli.inspect", SafetyError("secret-synthetic-cell"))
    diagnostics.record_reason(
        "cli.inspect", SafetyError("Excel worksheet exceeds the supported column limit.")
    )
    content = path.read_text()
    assert "cli.inspect sheet_selection" in content
    assert "cli.inspect column_limit" in content
    assert "secret-synthetic-cell" not in content


def test_ingestion_errors_have_safe_diagnostic_codes():
    tree = ast.parse((ROOT / "src/safeset/ingestion.py").read_text())
    messages = {
        node.exc.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "SafetyError"
        and node.exc.args
        and isinstance(node.exc.args[0], ast.Constant)
        and isinstance(node.exc.args[0].value, str)
    }
    assert messages <= diagnostics.REASON_CODES.keys()


def test_insecure_or_linked_log_is_never_written(tmp_path):
    path = diagnostics.log_path()
    path.parent.mkdir(mode=0o700)
    path.write_text("sentinel")
    path.chmod(0o644)
    assert not record("cli.inspect", "start")
    assert path.read_text() == "sentinel"
    path.unlink()
    target = tmp_path / "target"
    target.write_text("sentinel")
    path.symlink_to(target)
    assert not record("cli.inspect", "start")
    assert target.read_text() == "sentinel"
    path.unlink()
    path.parent.chmod(0o755)
    assert not record("cli.inspect", "start")
    assert not path.exists()


def test_cli_log_omits_source_values_and_paths(tmp_path):
    path = diagnostics.log_path()
    source = ROOT / "examples/synthetic_students.xlsx"
    result = CliRunner().invoke(app, ["inspect", str(source)])
    assert result.exit_code == 0
    missing = tmp_path / "secret-synthetic-filename.xlsx"
    rejected = CliRunner().invoke(app, ["inspect", str(missing)])
    assert rejected.exit_code != 0
    content = path.read_text()
    assert "cli.inspect source_read" in content
    assert "cli.inspect rejected" in content
    for value in ("SYNTH-001", "student_number", "synthetic_students", "secret-synthetic"):
        assert value not in content
