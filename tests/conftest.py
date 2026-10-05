import os
import stat
from pathlib import Path

import pytest

from safeset.ingestion import read_excel
from safeset.policy import load_policy
from safeset.storage import private_directory
from safeset.transform import sanitise

ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "synthetic-test-only-passphrase"


def assert_private_file(path: Path) -> None:
    if os.name == "nt":
        from safeset.windows_storage import validate_private

        validate_private(path, directory=False)
    else:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.fixture(autouse=True)
def private_diagnostic_log(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "safeset.diagnostics.log_path", lambda: tmp_path / "diagnostics" / "safeset.log"
    )


@pytest.fixture
def policy():
    return load_policy(ROOT / "examples/example-policy.yaml")


@pytest.fixture
def source():
    return read_excel(ROOT / "examples/synthetic_students.xlsx")


@pytest.fixture
def candidate(source, policy):
    return sanitise(source, policy)


@pytest.fixture
def destinations(tmp_path):
    for name in ["maps", "exports", "private"]:
        private_directory(tmp_path / name, create=True)
    return tmp_path / "exports/safe.xlsx", tmp_path / "maps/identity.enc"
