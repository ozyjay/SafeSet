"""Bounded, single-sheet Excel ingestion preserving text identifiers."""

import io
import stat
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import Workbook, load_workbook

from .errors import SafetyError

MAX_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED = 50 * 1024 * 1024
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


def _check_archive(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (
                not entries
                or len(entries) > 1000
                or sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED
                or any(entry.flag_bits & 1 for entry in entries)
            ):
                raise SafetyError("Excel workbook exceeds supported archive limits.")
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or any(
                name.startswith("/") or ".." in Path(name).parts for name in names
            ):
                raise SafetyError("Excel workbook has an unsafe archive structure.")
            forbidden = ("vba", "externallinks/", "embeddings/", "connections", "querytables/")
            if any(any(part in name.lower() for part in forbidden) for name in names):
                raise SafetyError("Excel workbook contains unsupported active content.")
    except (zipfile.BadZipFile, OSError, ValueError):
        raise SafetyError("Input is not a supported Excel workbook.") from None


def _cell_text(cell) -> str:
    value = cell.value
    if value is None:
        return ""
    if cell.data_type not in {"s", "n", "inlineStr"} or isinstance(
        value, (bool, date, datetime, time)
    ):
        raise SafetyError("Excel workbook contains an unsupported cell type.")
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    raise SafetyError("Excel workbook contains an unsupported cell type.")


def read_excel(path: Path) -> Table:
    if path.suffix.lower() != ".xlsx":
        raise SafetyError("Only .xlsx Excel workbooks are supported.")
    data = read_bounded(path)
    _check_archive(data)
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=False, data_only=False)
        if len(workbook.sheetnames) != 1 or workbook._external_links:
            raise SafetyError("Excel workbook must contain one sheet and no external links.")
        sheet = workbook.active
        if (
            sheet.sheet_state != "visible"
            or sheet.max_row < 1
            or sheet.max_row > MAX_ROWS + 1
            or sheet.max_column > MAX_COLUMNS
            or sheet.merged_cells.ranges
            or sheet.tables
            or sheet.auto_filter.ref
            or sheet._charts
            or sheet._images
            or any(d.hidden for d in sheet.row_dimensions.values())
            or any(d.hidden for d in sheet.column_dimensions.values())
        ):
            raise SafetyError("Excel workbook has unsupported sheet structure or dimensions.")
        header = tuple(_cell_text(cell) for cell in sheet[1])
        if (
            not header
            or len(set(header)) != len(header)
            or any(
                not name
                or name != name.strip()
                or len(name) > 64
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)
                for name in header
            )
        ):
            raise SafetyError("Excel headings are missing, duplicated or malformed.")
        rows = []
        for cells in sheet.iter_rows(min_row=2, max_col=len(header)):
            if any(cell.hyperlink or cell.comment for cell in cells):
                raise SafetyError("Excel workbook contains unsupported cell features.")
            values = tuple(_cell_text(cell) for cell in cells)
            if all(value == "" for value in values) or any(
                len(value) > MAX_FIELD or "\x00" in value for value in values
            ):
                raise SafetyError("Excel row shape or field size is invalid.")
            rows.append(dict(zip(header, values, strict=True)))
        if any(cell.hyperlink or cell.comment for cell in sheet[1]):
            raise SafetyError("Excel workbook contains unsupported cell features.")
        return Table(header, tuple(rows))
    except SafetyError:
        raise
    except Exception:
        raise SafetyError("Input is not a supported Excel workbook.") from None


def require_excel_path(path: Path) -> None:
    if path.suffix.lower() != ".xlsx":
        raise SafetyError("Excel output must have an .xlsx filename.")


def excel_bytes(table: Table) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "SafeSet"
    sheet.append(table.columns)
    for row in table.rows:
        sheet.append(tuple(row[name] for name in table.columns))
    for cells in sheet:
        for cell in cells:
            cell.data_type = "s"
            cell.number_format = "@"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
