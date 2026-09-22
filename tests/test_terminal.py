"""Exercise actual hidden passphrase prompts in a POSIX pseudo-terminal."""

import errno
import os
import pty
import select
import signal
import sys
import time
from pathlib import Path

from safeset.ingestion import read_excel

from .conftest import PASSPHRASE, ROOT


def run_terminal(arguments: list[str], prompts: list[bytes]) -> bytes:
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, "-m", "safeset", *arguments])
    transcript = b""
    answered = 0
    deadline = time.monotonic() + 15
    completed = False
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(fd, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    chunk = b""
                if not chunk:
                    break
                transcript += chunk
                if answered < len(prompts) and prompts[answered] in transcript:
                    os.write(fd, PASSPHRASE.encode() + b"\n")
                    answered += 1
            result, status = os.waitpid(pid, os.WNOHANG)
            if result:
                completed = True
                assert os.waitstatus_to_exitcode(status) == 0, transcript
                break
        if not completed:
            result, status = os.waitpid(pid, os.WNOHANG)
            if result:
                completed = True
                assert os.waitstatus_to_exitcode(status) == 0, transcript
            else:
                # EOF can arrive just before exit; a bounded polling wait handles that race.
                while time.monotonic() < deadline:
                    result, status = os.waitpid(pid, os.WNOHANG)
                    if result:
                        completed = True
                        assert os.waitstatus_to_exitcode(status) == 0, transcript
                        break
                    time.sleep(0.01)
        assert completed, "Terminal command timed out"
        assert answered == len(prompts)
        assert PASSPHRASE.encode() not in transcript
        return transcript
    finally:
        os.close(fd)
        if not completed:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)


def test_real_terminal_round_trip(destinations: tuple[Path, Path]):
    output, mapping = destinations
    run_terminal(
        [
            "sanitise",
            str(ROOT / "examples/synthetic_students.xlsx"),
            "--policy",
            str(ROOT / "examples/example-policy.yaml"),
            "--output",
            str(output),
            "--create-map",
            "--map",
            str(mapping),
            "--approve-export",
        ],
        [b"Mapping passphrase: ", b"Confirm mapping passphrase: "],
    )
    restored = output.parent.parent / "private/restored.xlsx"
    run_terminal(
        [
            "restore",
            str(output),
            "--map",
            str(mapping),
            "--output",
            str(restored),
            "--authorise",
            "--result-column",
            "campus",
            "--result-column",
            "subject",
            "--result-column",
            "gpa",
        ],
        [b"Mapping passphrase: "],
    )
    assert read_excel(restored).rows[0]["student_number"] == "SYNTH-001"
