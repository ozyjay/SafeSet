"""Real C# transport and relocated Windows helper tests using synthetic DOCX only."""

import json
import os
import shutil
import subprocess
import sys

import pytest
from openpyxl import load_workbook

from safeset.ingestion import read_excel
from tests.conftest import PASSPHRASE, ROOT
from tests.test_document import docx_bytes, text_parts

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows backend integration")
HARNESS = ROOT / "build/windows-backend-tests/bin/net10.0/BackendTests.dll"
HELPER = ROOT / "windows/SafeSetWindowsUX/engine/SafeSetHelper"


class Driver:
    def __init__(self, mode, executable, directory):
        environment = dict(os.environ)
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        self.process = subprocess.Popen(
            ["dotnet", str(HARNESS), mode, str(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=directory,
            env=environment,
            text=True,
            encoding="utf-8",
        )

    def call(self, command, payload):
        self.process.stdin.write(json.dumps({"command": command, "payload": payload}) + "\n")
        self.process.stdin.flush()
        response = self.process.stdout.readline()
        assert PASSPHRASE not in response
        result = json.loads(response)
        return result

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=10)
            self.process.stdout.close()


@pytest.fixture
def driver(tmp_path, request):
    if not HARNESS.exists():
        pytest.skip("Build windows/BackendTests before native backend verification")
    if request.param == "bundled":
        if not (HELPER / "SafeSetHelper.exe").exists():
            pytest.skip("Build the Windows helper before relocated verification")
        relocated = tmp_path / "relocated-engine"
        shutil.copytree(HELPER, relocated)
        native = Driver("bundled", relocated / "SafeSetHelper.exe", tmp_path)
    else:
        native = Driver("python", sys.executable, tmp_path)
    try:
        yield native
    finally:
        native.close()


@pytest.mark.parametrize("driver", ["python", "bundled"], indirect=True)
def test_native_document_review_cancel_integrity_and_round_trip(driver, tmp_path):
    source = tmp_path / "synthetic-source.docx"
    source.write_bytes(docx_bytes("<w:p><w:r><w:t>Synthetic Author</w:t></w:r></w:p>"))
    exports = tmp_path / "exports"
    exports.mkdir()
    output = exports / "synthetic-protected.docx"
    bundle = tmp_path / "new-private-maps/synthetic.enc"
    restored = tmp_path / "synthetic-restored.docx"
    assert driver.call("hello", {})["result"]["desktop_contract"] == "shared"
    content = driver.call("review_document_content", {"source": str(source)})["result"]
    payload = {
        "source": str(source),
        "output": str(output),
        "bundle": str(bundle),
        "terms": [{"value": "Synthetic Author", "kind": "other"}],
        "remove_comments": True,
        "review_digest": content["source_digest"],
        "reviewed_figures": [],
        "remove_paragraphs": [],
    }
    review = driver.call("prepare_document_protection", payload)["result"]
    assert "Synthetic Author" not in json.dumps(review)
    assert not output.exists() and not bundle.exists()
    driver.call("cancel", {})
    assert not driver.call(
        "approve_document_protection", {"review_id": review["review_id"], "passphrase": PASSPHRASE}
    )["ok"]
    assert not output.exists() and not bundle.exists()
    review = driver.call("prepare_document_protection", payload)["result"]
    assert driver.call(
        "approve_document_protection", {"review_id": review["review_id"], "passphrase": PASSPHRASE}
    )["ok"]
    assert "Synthetic Author" not in text_parts(output.read_bytes())
    restoration = {"returned": str(output), "bundle": str(bundle), "output": str(restored)}
    assert not driver.call(
        "prepare_document_restoration", {**restoration, "passphrase": "synthetic-wrong-passphrase"}
    )["ok"]
    review = driver.call("prepare_document_restoration", {**restoration, "passphrase": PASSPHRASE})[
        "result"
    ]
    assert not restored.exists()
    assert driver.call("approve_document_restoration", {"review_id": review["review_id"]})["ok"]
    assert "Synthetic Author" in text_parts(restored.read_bytes())
    assert not driver.call("approve_document_restoration", {"review_id": review["review_id"]})["ok"]


@pytest.mark.parametrize("driver", ["python", "bundled"], indirect=True)
def test_native_approval_rejects_stale_document(driver, tmp_path):
    source = tmp_path / "synthetic-source.docx"
    source.write_bytes(docx_bytes("<w:p><w:r><w:t>Synthetic Author</w:t></w:r></w:p>"))
    output = tmp_path / "synthetic-protected.docx"
    bundle = tmp_path / "maps/synthetic.enc"
    # Separate export directory, created for the synthetic fixture only.
    exports = tmp_path / "exports"
    exports.mkdir()
    output = exports / output.name
    review = driver.call(
        "prepare_document_protection",
        {
            "source": str(source),
            "output": str(output),
            "bundle": str(bundle),
            "terms": [],
            "remove_comments": True,
        },
    )["result"]
    source.write_bytes(docx_bytes("<w:p><w:r><w:t>Synthetic changed source</w:t></w:r></w:p>"))
    assert not driver.call(
        "approve_document_protection",
        {
            "review_id": review["review_id"],
            "passphrase": PASSPHRASE,
        },
    )["ok"]
    assert not output.exists() and not bundle.exists()


@pytest.mark.parametrize(
    "frame",
    [
        'b"broken\\n"',
        'json.dumps({"version": 9, "id": q["id"], "ok": True, "result": {}}).encode()+b"\\n"',
        'json.dumps({"version": 1, "id": "wrong", "ok": True, "result": {}}).encode()+b"\\n"',
        'b\'{"version":1,"version":1,"id":"\'+q["id"].encode()+b\'","ok":true,"result":{}}\\n\'',
        'b"x"*(1024*1024+1)+b"\\n"',
        'b"\\xff\\n"',
        'b"truncated"',
    ],
)
def test_native_transport_rejects_malformed_frames(tmp_path, frame):
    if not HARNESS.exists():
        pytest.skip("Build the native backend test harness first")
    # No secrets in arguments or fake programme; exercise actual C# frame parsing.
    code = (
        "import json,sys; q=json.loads(sys.stdin.buffer.readline()); sys.stdout.buffer.write("
        + frame
        + "); sys.stdout.buffer.flush()"
    )
    python_script = tmp_path / "synthetic-fake-helper.py"
    python_script.write_text(code, encoding="utf-8")
    native = Driver("fake:" + str(python_script), sys.executable, tmp_path)
    try:
        assert native.call("hello", {}) == {"ok": False, "error": "backend_rejected"}
    finally:
        native.close()


@pytest.mark.parametrize("driver", ["python", "bundled"], indirect=True)
def test_native_workbook_policy_review_and_approved_results(driver, tmp_path):
    source = ROOT / "examples/synthetic_students.xlsx"
    exports = tmp_path / "exports"
    exports.mkdir()
    output = exports / "synthetic-protected.xlsx"
    bundle = tmp_path / "maps/synthetic.enc"
    policy = driver.call(
        "load_policy",
        {
            "source": str(source),
            "sheet": None,
            "policy": str(ROOT / "examples/example-policy.yaml"),
        },
    )["result"]
    review = driver.call(
        "prepare_protection",
        {
            "source": str(source),
            "sheet": None,
            "output": str(output),
            "bundle": str(bundle),
            "drafts": policy["drafts"],
            "threshold": str(policy["threshold"]),
        },
    )["result"]
    assert review["validation"]["passed"]
    assert not output.exists() and not bundle.exists()
    assert driver.call(
        "approve_protection",
        {
            "review_id": review["review_id"],
            "passphrase": PASSPHRASE,
        },
    )["ok"]
    returned = tmp_path / "synthetic-returned.xlsx"
    workbook = load_workbook(output)
    column = workbook.active.max_column + 1
    workbook.active.cell(1, column, "synthetic_team")
    for row in range(2, workbook.active.max_row + 1):
        workbook.active.cell(row, column, "Synthetic team")
    workbook.save(returned)
    workbook.close()
    restored = tmp_path / "synthetic-restored.xlsx"
    request = {
        "returned": str(returned),
        "source": str(source),
        "bundle": str(bundle),
        "output": str(restored),
        "passphrase": PASSPHRASE,
        "returned_sheet": None,
        "source_sheet": None,
    }
    review = driver.call("prepare_reconstruction", request)["result"]
    assert review["new_columns"] == ["synthetic_team"]
    assert not driver.call(
        "approve_reconstruction",
        {
            "review_id": review["review_id"],
            "approved_results": [],
            "approved_sheets": [],
        },
    )["ok"]
    assert not restored.exists()
    review = driver.call("prepare_reconstruction", request)["result"]
    assert driver.call(
        "approve_reconstruction",
        {
            "review_id": review["review_id"],
            "approved_results": ["synthetic_team"],
            "approved_sheets": [],
        },
    )["ok"]
    restored_table = read_excel(restored)
    assert restored_table.rows[0]["student_number"] == "SYNTH-001"
    assert restored_table.rows[0]["synthetic_team"] == "Synthetic team"
