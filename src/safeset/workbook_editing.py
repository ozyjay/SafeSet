"""Explicit editable fields and surgical updates to a bound local workbook."""

import hashlib
import io
import posixpath
import zipfile
from pathlib import Path
from xml.dom import minidom

from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple

from .classification import canonical_numeric
from .errors import SafetyError
from .ingestion import MAX_BYTES, _check_archive, read_bounded, read_excel_sheets
from .policy import ColumnRule, Policy

EDIT_ACTIONS = {"keep", "code", "keep_numeric"}
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def file_digest(path: Path) -> str:
    return hashlib.sha256(read_bounded(path)).hexdigest()


def validate_editable_fields(value: object, policies: dict[str, Policy]) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != set(policies)
        or any(
            not isinstance(columns, list)
            or any(not isinstance(name, str) for name in columns)
            or len(columns) != len(set(columns))
            or any(
                name not in policies[sheet].columns
                or policies[sheet].columns[name].action not in EDIT_ACTIONS
                for name in columns
            )
            for sheet, columns in value.items()
        )
    ):
        raise SafetyError("Editable fields must be explicitly selected reversible fields.")
    return value


def edit_codebooks(bundle: dict) -> dict:
    books = {}
    shared = {name: {} for name in bundle["shared_code_fields"]}
    for sheet, item in bundle["sheets"].items():
        for name, book in item["codebooks"].items():
            reverse = {code: label for label, code in book.items()}
            books[sheet, name] = reverse
            if name in shared:
                shared[name].update(reverse)
    for sheet, item in bundle["sheets"].items():
        for name in item["codebooks"]:
            if name in shared:
                books[sheet, name] = shared[name]
    return books


def decoded_edit(value: str, rule: ColumnRule, codes: dict[str, str]) -> str:
    """Resolve an allowed returned value; never infer identities or new categories."""
    if rule.action == "keep" and value in rule.allowed_values:
        return value
    if rule.action == "keep_numeric":
        canonical = canonical_numeric(value, rule.bounds, rule.max_decimal_places)
        if canonical is not None:
            return canonical
    if rule.action == "code" and value in codes:
        return codes[value]
    raise SafetyError("An edited value is outside its approved category or numeric domain.")


def source_coordinates(path: Path, sheets: tuple[str, ...]) -> tuple[dict, dict]:
    coordinates = {sheet: [] for sheet in sheets}
    tables = read_excel_sheets(
        path, sheets, allow_cached_formulas=True, allow_source_dates=True,
        observe_cell=lambda sheet, coordinate, _value: coordinates[sheet].append(coordinate),
    )
    rows = {}
    for sheet, table in tables.items():
        width = len(table.columns)
        cells = coordinates[sheet]
        if len(cells) != width * len(table.rows) or len(set(cells)) != len(cells):
            raise SafetyError("Editable workbook cell locations are ambiguous.")
        rows[sheet] = [
            dict(zip(table.columns, cells[start:start + width], strict=True))
            for start in range(0, len(cells), width)
        ]
    return tables, rows


def validate_editable_layout(path: Path, fields: dict) -> None:
    _, coordinates = source_coordinates(path, tuple(fields))
    workbook = load_workbook(io.BytesIO(read_bounded(path)), data_only=False)
    try:
        if any(
            workbook[sheet][row[name]].data_type in {"f", "d"}
            for sheet, names in fields.items()
            for row in coordinates[sheet]
            for name in names
        ):
            raise SafetyError("Formula and date cells cannot be selected for editing.")
    finally:
        workbook.close()


def _xml(data: bytes):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise SafetyError("Editable workbook XML is unsupported.")
    return minidom.parseString(data)


def patched_workbook_bytes(path: Path, bundle: dict, restored: dict) -> bytes:
    """Keep untouched ZIP members byte-for-byte; patch authorised cells in source order."""
    data = read_bounded(path)
    if hashlib.sha256(data).hexdigest() != bundle["source_file_digest"]:
        raise SafetyError("Original workbook does not match the relational restoration bundle.")
    _check_archive(data)
    sources, coordinates = source_coordinates(path, tuple(bundle["sheets"]))
    if file_digest(path) != bundle["source_file_digest"]:
        raise SafetyError("A workbook changed after relational restoration review.")
    edits = {}
    for sheet, names in bundle["editable_fields"].items():
        edits[sheet] = {}
        for index, source_row in enumerate(sources[sheet].rows):
            for name in names:
                value = restored[sheet].rows[index][name]
                if value != source_row[name]:
                    rule = bundle["sheets"][sheet]["policy"]["columns"][name]
                    edits[sheet][coordinates[sheet][index][name]] = (
                        value, rule["action"] == "keep_numeric"
                    )
    if not any(edits.values()):
        return data
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            workbook = _xml(archive.read("xl/workbook.xml"))
            relationships = _xml(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {}
            for relation in relationships.getElementsByTagNameNS(PACKAGE_REL, "Relationship"):
                if relation.getAttribute("TargetMode") == "External":
                    continue
                target = relation.getAttribute("Target")
                targets[relation.getAttribute("Id")] = (
                    target.lstrip("/") if target.startswith("/")
                    else posixpath.normpath(posixpath.join("xl", target))
                )
            replacements = {}
            for sheet in workbook.getElementsByTagNameNS(MAIN, "sheet"):
                changes = edits.get(sheet.getAttribute("name"), {})
                if not changes:
                    continue
                member = targets[sheet.getAttributeNS(REL, "id")]
                if not member.startswith("xl/worksheets/") or member in replacements:
                    raise SafetyError("Editable workbook cell locations are ambiguous.")
                document = _xml(archive.read(member))
                sheet_data = document.getElementsByTagNameNS(MAIN, "sheetData")
                if len(sheet_data) != 1:
                    raise SafetyError("Editable workbook XML is unsupported.")
                row_elements = {
                    int(row.getAttribute("r")): row
                    for row in sheet_data[0].getElementsByTagNameNS(MAIN, "row")
                }
                for coordinate, (value, numeric) in changes.items():
                    row_number, column = coordinate_to_tuple(coordinate)
                    row = row_elements[row_number]
                    cells = list(row.getElementsByTagNameNS(MAIN, "c"))
                    cell = next((c for c in cells if c.getAttribute("r") == coordinate), None)
                    prefix = row.prefix + ":" if row.prefix else ""
                    if cell is None:
                        cell = document.createElementNS(MAIN, prefix + "c")
                        cell.setAttribute("r", coordinate)
                        after = next((c for c in cells if coordinate_to_tuple(
                            c.getAttribute("r"))[1] > column), None)
                        row.insertBefore(cell, after)
                    for child in list(cell.childNodes):
                        cell.removeChild(child)
                    if cell.hasAttribute("t"):
                        cell.removeAttribute("t")
                    if numeric and value:
                        node = document.createElementNS(MAIN, prefix + "v")
                        node.appendChild(document.createTextNode(value))
                        cell.appendChild(node)
                    elif value:
                        cell.setAttribute("t", "inlineStr")
                        inline = document.createElementNS(MAIN, prefix + "is")
                        text = document.createElementNS(MAIN, prefix + "t")
                        text.appendChild(document.createTextNode(value))
                        inline.appendChild(text)
                        cell.appendChild(inline)
                replacements[member] = document.toxml(encoding="utf-8")
            if len(replacements) != sum(bool(changes) for changes in edits.values()):
                raise SafetyError("Editable workbook cell locations are ambiguous.")
            # Excel recalculates original formulas locally when opening the restored copy.
            calculation = workbook.getElementsByTagNameNS(MAIN, "calcPr")
            if calculation:
                calculation = calculation[0]
            else:
                root = workbook.documentElement
                prefix = root.prefix + ":" if root.prefix else ""
                calculation = workbook.createElementNS(MAIN, prefix + "calcPr")
                root.insertBefore(calculation, next((node for node in root.childNodes
                    if node.localName in {"oleSize", "customWorkbookViews", "pivotCaches",
                                          "smartTagPr", "smartTagTypes", "webPublishing",
                                          "fileRecoveryPr", "webPublishObjects", "extLst"}), None))
            calculation.setAttribute("calcMode", "auto")
            calculation.setAttribute("fullCalcOnLoad", "1")
            calculation.setAttribute("forceFullCalc", "1")
            replacements["xl/workbook.xml"] = workbook.toxml(encoding="utf-8")
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as result:
                for entry in archive.infolist():
                    result.writestr(entry, replacements.get(entry.filename)
                                    if entry.filename in replacements else archive.read(entry))
            encoded = output.getvalue()
            if len(encoded) > MAX_BYTES:
                raise SafetyError("Restored workbook exceeds the supported size limit.")
            return encoded
    except SafetyError:
        raise
    except Exception:
        raise SafetyError("Editable workbook XML is unsupported.") from None
