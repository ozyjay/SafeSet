"""Bounded CSV ingestion preserving exact strings."""

import csv
import io
import stat
from dataclasses import dataclass
from pathlib import Path

from .errors import SafetyError

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 128
MAX_FIELD = 4096


@dataclass(frozen=True)
class Table:
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


def read_bounded(path: Path, limit: int = MAX_BYTES) -> bytes:
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise SafetyError("Input must be a regular local file.")
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError:
        raise SafetyError("Unable to read the requested local file.") from None
    if len(data) > limit:
        raise SafetyError("Input exceeds the supported size limit.")
    return data


def read_csv(path: Path) -> Table:
    try:
        text = read_bounded(path).decode("utf-8-sig")
        if "\x00" in text:
            raise SafetyError("CSV contains prohibited control characters.")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, [])
        if (
            not header
            or len(header) > MAX_COLUMNS
            or len(set(header)) != len(header)
            or any(
                not c
                or c != c.strip()
                or len(c) > 64
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in c)
                for c in header
            )
        ):
            raise SafetyError("CSV headings are missing, duplicated or malformed.")
        rows = []
        for cells in reader:
            if len(cells) != len(header) or any(len(v) > MAX_FIELD for v in cells):
                raise SafetyError("CSV row shape or field size is invalid.")
            if len(rows) >= MAX_ROWS:
                raise SafetyError("CSV exceeds the supported row limit.")
            rows.append(dict(zip(header, cells, strict=True)))
        return Table(tuple(header), tuple(rows))
    except (UnicodeError, csv.Error):
        raise SafetyError("Input is not a supported UTF-8 CSV file.") from None


def csv_bytes(table: Table) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=table.columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(table.rows)
    return buffer.getvalue().encode("utf-8")
