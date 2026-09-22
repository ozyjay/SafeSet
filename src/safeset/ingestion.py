"""Bounded Excel ingestion preserving text identifiers."""

import io
import stat
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.utils.cell import column_index_from_string, range_boundaries

from .errors import SafetyError

MAX_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 128
MAX_FIELD = 4096
MAX_TABLES = 128


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


def list_excel_sheets(path: Path) -> tuple[str, ...]:
    """List visible worksheet names without reading cell values into the UI."""
    if path.suffix.lower() != ".xlsx":
        raise SafetyError("Only .xlsx Excel workbooks are supported.")
    data = read_bounded(path)
    _check_archive(data)
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
        if workbook._external_links:
            raise SafetyError("Excel workbook contains external links.")
        names = tuple(
            sheet.title for sheet in workbook.worksheets if sheet.sheet_state == "visible"
        )
        if not names:
            raise SafetyError("Excel workbook has no visible worksheet.")
        return names
    except SafetyError:
        raise
    except Exception:
        raise SafetyError("Input is not a supported Excel workbook.") from None


def _overlaps(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    a1, b1, a2, b2 = left
    c1, d1, c2, d2 = right
    return a1 <= c2 and c1 <= a2 and b1 <= d2 and d1 <= b2


def _read_region(
    worksheet,
    bounds: tuple[int, int, int, int],
    *,
    last_data_row: int | None = None,
) -> Table:
    min_col, min_row, max_col, max_row = bounds
    if (
        min_col < 1
        or min_row < 1
        or max_col < min_col
        or max_row < min_row
        or max_col - min_col + 1 > MAX_COLUMNS
        or (last_data_row if last_data_row is not None else max_row) - min_row > MAX_ROWS
    ):
        raise SafetyError("Excel table has unsupported dimensions.")
    if any(
        _overlaps(bounds, range_boundaries(str(merged))) for merged in worksheet.merged_cells.ranges
    ):
        raise SafetyError("Excel data range contains merged cells.")
    if any(
        dimension.hidden and min_row <= index <= max_row
        for index, dimension in worksheet.row_dimensions.items()
    ):
        raise SafetyError("Excel data range contains hidden rows.")
    for key, dimension in worksheet.column_dimensions.items():
        index = column_index_from_string(key)
        first = dimension.min or index
        last = dimension.max or index
        if dimension.hidden and first <= max_col and min_col <= last:
            raise SafetyError("Excel data range contains hidden columns.")
    header_cells = next(
        worksheet.iter_rows(min_row=min_row, max_row=min_row, min_col=min_col, max_col=max_col)
    )
    header = tuple(_cell_text(cell) for cell in header_cells)
    if not header or any(not name for name in header):
        raise SafetyError("Excel headings are missing.")
    if len(set(header)) != len(header):
        raise SafetyError("Excel headings are duplicated.")
    if any(
        name != name.strip() or len(name) > 64 or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)
        for name in header
    ):
        raise SafetyError("Excel headings contain unsupported text.")
    if any(cell.hyperlink or cell.comment for cell in header_cells):
        raise SafetyError("Excel workbook contains unsupported cell features.")
    rows = []
    data_end = last_data_row if last_data_row is not None else max_row
    for cells in (
        worksheet.iter_rows(
            min_row=min_row + 1,
            max_row=data_end,
            min_col=min_col,
            max_col=max_col,
        )
        if data_end > min_row
        else ()
    ):
        if any(cell.hyperlink or cell.comment for cell in cells):
            raise SafetyError("Excel workbook contains unsupported cell features.")
        values = tuple(_cell_text(cell) for cell in cells)
        if all(value == "" for value in values) or any(
            len(value) > MAX_FIELD or "\x00" in value for value in values
        ):
            raise SafetyError("Excel row shape or field size is invalid.")
        rows.append(dict(zip(header, values, strict=True)))
    return Table(header, tuple(rows))


def _read_worksheet(worksheet) -> Table:
    if worksheet.tables:
        if len(worksheet.tables) > MAX_TABLES:
            raise SafetyError("Excel worksheet exceeds the supported table count.")
        ranges = []
        for structured in worksheet.tables.values():
            if (
                structured.headerRowCount != 1
                or structured.connectionId is not None
                or structured.tableType not in {None, "worksheet"}
            ):
                raise SafetyError("Excel table has unsupported structure.")
            bounds = range_boundaries(structured.ref)
            if any(_overlaps(bounds, earlier) for earlier, _ in ranges):
                raise SafetyError("Excel tables overlap.")
            totals = structured.totalsRowCount or 0
            if totals not in {0, 1} or (structured.totalsRowShown and not totals):
                raise SafetyError("Excel table has unsupported totals metadata.")
            ranges.append((bounds, structured))
        ranges.sort(key=lambda item: (item[0][1], item[0][0]))
        tables = []
        for bounds, structured in ranges:
            data = _read_region(
                worksheet, bounds, last_data_row=bounds[3] - (structured.totalsRowCount or 0)
            )
            if (
                structured.tableColumns
                and tuple(column.name for column in structured.tableColumns) != data.columns
            ):
                raise SafetyError("Excel table headings differ from its metadata.")
            tables.append(data)
        header = tables[0].columns
        if any(table.columns != header for table in tables[1:]):
            raise SafetyError("Excel tables must have identical headings in the same order.")
        if sum(len(table.rows) for table in tables) > MAX_ROWS:
            raise SafetyError("Excel tables exceed the combined row limit.")
        return Table(header, tuple(row for table in tables for row in table.rows))
    occupied = tuple(
        cell
        for cell in worksheet._cells.values()
        if cell.value is not None or cell.hyperlink or cell.comment
    )
    if not occupied:
        raise SafetyError("Excel headings are missing.")
    last_row = max(cell.row for cell in occupied)
    last_column = max(cell.column for cell in occupied)
    if last_row > MAX_ROWS + 1:
        raise SafetyError("Excel worksheet exceeds the supported row limit.")
    if last_column > MAX_COLUMNS:
        raise SafetyError("Excel worksheet exceeds the supported column limit.")
    return _read_region(worksheet, (1, 1, last_column, last_row))


def read_excel(path: Path, sheet: str | tuple[str, ...] | None = None) -> Table:
    if path.suffix.lower() != ".xlsx":
        raise SafetyError("Only .xlsx Excel workbooks are supported.")
    data = read_bounded(path)
    _check_archive(data)
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=False, data_only=False)
        if workbook._external_links:
            raise SafetyError("Excel workbook contains external links.")
        visible = tuple(ws.title for ws in workbook.worksheets if ws.sheet_state == "visible")
        if sheet is None:
            if len(visible) != 1:
                raise SafetyError("Select one or more worksheets from the Excel workbook.")
            selected = visible
        elif isinstance(sheet, str):
            selected = (sheet,)
        elif isinstance(sheet, tuple):
            selected = sheet
        else:
            raise SafetyError("Worksheet selection is invalid.")
        if (
            not selected
            or len(set(selected)) != len(selected)
            or any(name not in visible for name in selected)
        ):
            raise SafetyError("Selected worksheet is missing, hidden or repeated.")
        tables = [_read_worksheet(workbook[name]) for name in selected]
        header = tables[0].columns
        if any(table.columns != header for table in tables[1:]):
            raise SafetyError("Selected worksheets must have identical headings in the same order.")
        if sum(len(table.rows) for table in tables) > MAX_ROWS:
            raise SafetyError("Selected worksheets exceed the combined row limit.")
        return Table(header, tuple(row for table in tables for row in table.rows))
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
