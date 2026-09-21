from pathlib import Path

import pytest

from safeset.ingestion import read_csv
from safeset.policy import load_policy
from safeset.transform import sanitise

ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "synthetic-test-only-passphrase"


@pytest.fixture
def policy():
    return load_policy(ROOT / "examples/example-policy.yaml")


@pytest.fixture
def source():
    return read_csv(ROOT / "examples/synthetic_students.csv")


@pytest.fixture
def candidate(source, policy):
    return sanitise(source, policy)


@pytest.fixture
def destinations(tmp_path):
    for name in ["maps", "exports", "private"]:
        (tmp_path / name).mkdir(mode=0o700)
    return tmp_path / "exports/safe.csv", tmp_path / "maps/identity.enc"
