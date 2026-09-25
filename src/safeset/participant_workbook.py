"""Bounded participant row replacement without rewriting unrelated workbook parts."""

import io
import posixpath
import zipfile
from decimal import Decimal

from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple, get_column_letter, range_boundaries

from .errors import SafetyError
from .ingestion import MAX_BYTES
from .workbook_editing import MAIN, PACKAGE_REL, REL, _xml, source_coordinates

LAYOUT_ERROR = "Participant changes need one plain range or Excel table with safe space below it."


def replace_participants(data, source_path, sheet, table, origins, numeric_fields):
    """Keep surviving cells and styles; new local values are literal text, never formulas."""
    sources, coordinates = source_coordinates(source_path, (sheet,))
    original = sources[sheet]
    if not original.rows or not table.rows or len(table.rows) != len(origins):
        raise SafetyError(LAYOUT_ERROR)
    locations = coordinates[sheet]
    first_row, first_col = coordinate_to_tuple(locations[0][original.columns[0]])
    width = len(original.columns)
    old_end = first_row + len(original.rows) - 1
    new_end = first_row + len(table.rows) - 1
    if any(
        coordinate_to_tuple(row[name]) != (first_row + index, first_col + offset)
        for index, row in enumerate(locations)
        for offset, name in enumerate(original.columns)
    ):
        raise SafetyError(LAYOUT_ERROR)
    book = load_workbook(io.BytesIO(data), data_only=False)
    try:
        worksheet = book[sheet]
        tables = list(worksheet.tables.values())
        if len(tables) > 1 or (not tables and (first_row != 2 or first_col != 1)):
            raise SafetyError(LAYOUT_ERROR)
        if tables and (
            range_boundaries(tables[0].ref)
            != (first_col, first_row - 1, first_col + width - 1, old_end)
            or tables[0].totalsRowCount
            or tables[0].totalsRowShown
        ):
            raise SafetyError(LAYOUT_ERROR)
        for merged in worksheet.merged_cells.ranges:
            if (
                merged.min_row <= max(old_end, new_end)
                and merged.max_row >= first_row
                and merged.min_col <= first_col + width - 1
                and merged.max_col >= first_col
            ):
                raise SafetyError(LAYOUT_ERROR)
        for row in worksheet.iter_rows(
            min_row=first_row,
            max_row=max(old_end, new_end),
            min_col=first_col,
            max_col=first_col + width - 1,
        ):
            for cell in row:
                if (
                    cell.data_type == "f"
                    or cell.comment
                    or cell.hyperlink
                    or (cell.row > old_end and cell.value is not None)
                ):
                    raise SafetyError(LAYOUT_ERROR)
        if any(
            worksheet.row_dimensions[index].hidden
            for index in range(first_row, max(old_end, new_end) + 1)
        ):
            raise SafetyError(LAYOUT_ERROR)
        if any(
            d.hidden and d.min <= first_col + width - 1 and d.max >= first_col
            for d in worksheet.column_dimensions.values()
        ):
            raise SafetyError(LAYOUT_ERROR)
        # These coordinate-bound features cannot safely follow moved participants.
        if worksheet.data_validations.count or len(worksheet.conditional_formatting):
            raise SafetyError(LAYOUT_ERROR)
        table_name = tables[0].name if tables else None
    finally:
        book.close()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if any(n.startswith("_xmlsignatures/") for n in archive.namelist()):
                raise SafetyError(LAYOUT_ERROR)
            workbook = _xml(archive.read("xl/workbook.xml"))
            relationships = _xml(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {}
            for relation in relationships.getElementsByTagNameNS(PACKAGE_REL, "Relationship"):
                key = relation.getAttribute("Id")
                if key in targets or relation.getAttribute("TargetMode") == "External":
                    raise SafetyError(LAYOUT_ERROR)
                target = relation.getAttribute("Target")
                targets[key] = (
                    target.lstrip("/")
                    if target.startswith("/")
                    else posixpath.normpath(posixpath.join("xl", target))
                )
            matches = [
                s
                for s in workbook.getElementsByTagNameNS(MAIN, "sheet")
                if s.getAttribute("name") == sheet
            ]
            if len(matches) != 1:
                raise SafetyError(LAYOUT_ERROR)
            member = targets[matches[0].getAttributeNS(REL, "id")]
            if not member.startswith("xl/worksheets/"):
                raise SafetyError(LAYOUT_ERROR)
            document = _xml(archive.read(member))
            containers = document.getElementsByTagNameNS(MAIN, "sheetData")
            if len(containers) != 1:
                raise SafetyError(LAYOUT_ERROR)
            container = containers[0]
            prefix = container.prefix + ":" if container.prefix else ""
            rows, cells = {}, {}
            for row in container.getElementsByTagNameNS(MAIN, "row"):
                number = int(row.getAttribute("r"))
                if number in rows:
                    raise SafetyError(LAYOUT_ERROR)
                rows[number] = row
                for cell in row.getElementsByTagNameNS(MAIN, "c"):
                    ref = cell.getAttribute("r")
                    if ref in cells or coordinate_to_tuple(ref)[0] != number:
                        raise SafetyError(LAYOUT_ERROR)
                    cells[ref] = cell.cloneNode(True)
            for number in range(first_row, max(old_end, new_end) + 1):
                row = rows.get(number)
                if row is None:
                    row = document.createElementNS(MAIN, prefix + "row")
                    row.setAttribute("r", str(number))
                    container.insertBefore(
                        row, next((r for n, r in sorted(rows.items()) if n > number), None)
                    )
                    rows[number] = row
                for cell in list(row.getElementsByTagNameNS(MAIN, "c")):
                    col = coordinate_to_tuple(cell.getAttribute("r"))[1]
                    if first_col <= col < first_col + width:
                        row.removeChild(cell)
                if number > new_end:
                    continue
                index = number - first_row
                origin = origins[index]
                for offset, name in enumerate(table.columns):
                    col = first_col + offset
                    ref = f"{get_column_letter(col)}{number}"
                    old_index = origin if origin is not None else len(original.rows) - 1
                    old_ref = f"{get_column_letter(col)}{first_row + old_index}"
                    template = cells.get(old_ref)
                    cell = (
                        template.cloneNode(True)
                        if template
                        else document.createElementNS(MAIN, prefix + "c")
                    )
                    cell.setAttribute("r", ref)
                    if origin is None:
                        # Only style is inherited for new participants. No metadata or formulas.
                        style = cell.getAttribute("s")
                        cell = document.createElementNS(MAIN, prefix + "c")
                        cell.setAttribute("r", ref)
                        if style:
                            cell.setAttribute("s", style)
                        value = table.rows[index][name]
                        if value and name in numeric_fields:
                            if len(value.replace(".", "").lstrip("0").rstrip("0")) > 15 or Decimal(
                                str(float(value))
                            ) != Decimal(value):
                                raise SafetyError(
                                    "An edited number exceeds Excel's supported precision."
                                )
                            node = document.createElementNS(MAIN, prefix + "v")
                            node.appendChild(document.createTextNode(value))
                            cell.appendChild(node)
                        elif value:
                            cell.setAttribute("t", "inlineStr")
                            inline = document.createElementNS(MAIN, prefix + "is")
                            text = document.createElementNS(MAIN, prefix + "t")
                            text.setAttribute("xml:space", "preserve")
                            text.appendChild(document.createTextNode(value))
                            inline.appendChild(text)
                            cell.appendChild(inline)
                    after = next(
                        (
                            c
                            for c in row.getElementsByTagNameNS(MAIN, "c")
                            if coordinate_to_tuple(c.getAttribute("r"))[1] > col
                        ),
                        None,
                    )
                    row.insertBefore(cell, after)
            start = f"{get_column_letter(first_col)}{first_row - 1}"
            new_ref = f"{start}:{get_column_letter(first_col + width - 1)}{new_end}"
            for dimension in document.getElementsByTagNameNS(MAIN, "dimension"):
                left, top, right, bottom = range_boundaries(dimension.getAttribute("ref"))
                end_column = get_column_letter(max(right, first_col + width - 1))
                end = f"{end_column}{max(bottom, new_end)}"
                dimension.setAttribute("ref", f"{get_column_letter(left)}{top}:{end}")
            for autofilter in document.getElementsByTagNameNS(MAIN, "autoFilter"):
                if range_boundaries(autofilter.getAttribute("ref")) != (
                    first_col,
                    first_row - 1,
                    first_col + width - 1,
                    old_end,
                ):
                    raise SafetyError(LAYOUT_ERROR)
                autofilter.setAttribute("ref", new_ref)
            replacements = {member: document.toxml(encoding="utf-8")}
            if table_name:
                found = []
                for entry in archive.namelist():
                    if entry.startswith("xl/tables/") and entry.endswith(".xml"):
                        doc = _xml(archive.read(entry))
                        root = doc.documentElement
                        if root.getAttribute("name") == table_name:
                            if doc.getElementsByTagNameNS(MAIN, "calculatedColumnFormula"):
                                raise SafetyError(LAYOUT_ERROR)
                            root.setAttribute("ref", new_ref)
                            for auto in doc.getElementsByTagNameNS(MAIN, "autoFilter"):
                                auto.setAttribute("ref", new_ref)
                            replacements[entry] = doc.toxml(encoding="utf-8")
                            found.append(entry)
                if len(found) != 1:
                    raise SafetyError(LAYOUT_ERROR)
            calculation = workbook.getElementsByTagNameNS(MAIN, "calcPr")
            if not calculation:
                raise SafetyError(LAYOUT_ERROR)
            calculation[0].setAttribute("calcMode", "auto")
            calculation[0].setAttribute("fullCalcOnLoad", "1")
            calculation[0].setAttribute("forceFullCalc", "1")
            replacements["xl/workbook.xml"] = workbook.toxml(encoding="utf-8")
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as result:
                for entry in archive.infolist():
                    result.writestr(entry, replacements.get(entry.filename, archive.read(entry)))
            encoded = output.getvalue()
            if len(encoded) > MAX_BYTES:
                raise SafetyError(LAYOUT_ERROR)
            return encoded
    except SafetyError:
        raise
    except Exception:
        raise SafetyError(LAYOUT_ERROR) from None
