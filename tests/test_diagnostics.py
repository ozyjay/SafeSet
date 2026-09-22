import stat

from typer.testing import CliRunner

from safeset import diagnostics
from safeset.cli import app
from safeset.diagnostics import record
from safeset.errors import SafetyError

from .conftest import ROOT


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
    content = path.read_text()
    assert "cli.inspect sheet_selection" in content
    assert "secret-synthetic-cell" not in content


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
