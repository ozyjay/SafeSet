"""Bounded local JSON-line bridge for native desktops. Never log requests."""

import json
import sys
from pathlib import Path

from .desktop_flow import (
    approve_export,
    approve_protection,
    approve_reconstruction,
    approve_relational_protection,
    approve_relational_reconstruction,
    inspect_returned,
    inspect_source,
    locate_unsafe_source_cells,
    prepare_export,
    prepare_protection,
    prepare_reconstruction,
    prepare_relational_protection,
    prepare_relational_reconstruction,
    restore_results,
)
from .document import DocumentTerm, inspect_document
from .document_flow import (
    approve_document_protection,
    approve_document_restoration,
    prepare_document_protection,
    prepare_document_restoration,
)
from .errors import SafetyError
from .ingestion import list_excel_sheets
from .policy_authoring import RuleDraft, load_drafts, local_category_review, save_policy
from .pseudonyms import new_id

PROTOCOL_VERSION = 1
MAX_REQUEST = 1024 * 1024
MAX_RESPONSE = 1024 * 1024

# Only fixed, value-free codes cross the desktop boundary. Unknown errors stay generic.
PUBLIC_SAFETY_ERRORS = {
    "Policy schema or safety constraints are invalid; see policy-format.md.": (
        "policy_configuration"
    ),
    "Every source field needs an explicit protection decision.": "field_decisions",
    "Every selected worksheet needs explicit field decisions.": "field_decisions",
    "Every selected worksheet needs an explicit policy.": "field_decisions",
    "Source keys must be non-empty and safe text.": "source_key_invalid",
    "Source keys must be non-empty and unique.": "source_key_invalid",
    "Source worksheets use a reserved relational heading.": "reserved_heading",
    "Empty worksheets cannot be exported.": "empty_worksheet",
    "Source category is outside the approved domain.": "category_domain",
    "Numeric input violates approved bounds or format.": "numeric_domain",
    "A numeric input cannot be binned.": "numeric_domain",
    "Non-finite numeric input is prohibited.": "numeric_domain",
    "Numeric input falls outside approved bins.": "numeric_domain",
    "Added analysis worksheet structure is invalid.": "analysis_sheet",
    "Added analysis worksheet contains unsafe content.": "analysis_sheet",
    "Every added analysis worksheet requires explicit approval.": "analysis_sheet_approval",
    "Excel formula has no saved result. Recalculate and save locally.": "formula_result",
    "Excel data range contains hidden rows.": "hidden_data",
    "Excel data range contains hidden columns.": "hidden_data",
    "Returned workbook contains hidden worksheets.": "hidden_worksheet",
    "Excel data range contains merged cells.": "merged_data",
    "Excel workbook contains unsupported active content.": "active_content",
    "Excel workbook contains unsupported cell features.": "cell_features",
    "Excel workbook contains an unsupported cell type.": "cell_type",
    "Destination already exists; overwriting is prohibited.": "destination_exists",
    "Mapping destination already exists; overwriting is prohibited.": "destination_exists",
    "Output directory must already exist.": "output_directory",
    "Operational artefacts must be stored outside repositories.": "repository_destination",
    "Mapping and export must use separate storage directories.": "destination_separation",
    "Every shared obfuscation field must be coded in at least two selected worksheets.": (
        "shared_code_configuration"
    ),
    "Restoration bundle could not be authenticated or decoded.": "bundle_authentication",
    "Relational restoration bundle could not be authenticated or decoded.": "bundle_authentication",
    "Unable to access private restoration bundle.": "bundle_unavailable",
    "Unable to access private relational restoration bundle.": "bundle_unavailable",
    "Restoration bundle version or structure is unsupported.": "bundle_incompatible",
    "Restoration bundle version or envelope is unsupported.": "bundle_incompatible",
    "Relational restoration bundle version or structure is unsupported.": "bundle_incompatible",
    "Relational restoration bundle envelope is unsupported.": "bundle_incompatible",
    "Original source does not match the restoration bundle.": "source_mismatch",
    "Original workbook does not match the relational restoration bundle.": "source_mismatch",
    "Original source identities do not match the bundle.": "source_mismatch",
    "Original worksheet schema does not match the bundle.": "source_mismatch",
    "Original source violates the bound protection policy.": "source_mismatch",
    "Original category is absent from the restoration bundle.": "source_mismatch",
    "Returned relational workbook worksheet coverage does not match the bundle.": (
        "worksheet_coverage"
    ),
    "Relational workbook worksheet coverage does not match the bundle.": (
        "worksheet_coverage"
    ),
    "Protected workbook schema has changed unexpectedly.": "protected_schema",
    "Protected worksheet schema has changed unexpectedly.": "protected_schema",
    "Returned workbook contains unexpected or colliding fields.": "result_schema",
    "Returned relational workbook contains unexpected fields.": "result_schema",
    "Returned record IDs are malformed or duplicated.": "record_ids",
    "Returned record coverage does not match the bundle.": "record_coverage",
    "Returned relational record coverage does not match the bundle.": "record_coverage",
    "Returned relational entity linkage has changed.": "entity_linkage",
    "A protected source field was changed.": "protected_value",
    "New result contains unsafe or unsupported spreadsheet text.": "result_text",
    "Original source contains unsafe spreadsheet text.": "source_text",
    "A workbook changed after restoration review.": "stale_review",
    "A workbook changed after relational restoration review.": "stale_review",
    "Every new result field requires explicit approval.": "result_approval",
    "Every new relational result field requires explicit approval.": "result_approval",
    "Input must be a regular local file.": "input_unavailable",
    "Unable to read the requested local file.": "input_unavailable",
    "Input is not a supported Excel workbook.": "workbook_invalid",
    "Only .xlsx Excel workbooks are supported.": "workbook_invalid",
    "Excel workbook has an unsafe archive structure.": "workbook_invalid",
    "Excel workbook exceeds supported archive limits.": "workbook_limit",
    "Input exceeds the supported size limit.": "workbook_limit",
    "Excel worksheet exceeds the supported row limit.": "workbook_limit",
    "Excel worksheet exceeds the supported column limit.": "workbook_limit",
    "Excel headings are missing.": "workbook_headings",
    "Excel headings are duplicated.": "workbook_headings",
    "Excel headings contain unsupported text.": "workbook_headings",
    "Excel row shape or field size is invalid.": "workbook_structure",
    "Excel workbook has no visible worksheet.": "sheet_selection",
    "Select one or more worksheets from the Excel workbook.": "sheet_selection",
    "Worksheet selection is invalid.": "sheet_selection",
    "Selected worksheet is missing, hidden or repeated.": "sheet_selection",
    "Select one or more distinct worksheets.": "sheet_selection",
    "Selected worksheet is missing or hidden.": "sheet_selection",
    "Selected worksheets must have identical headings in the same order.": "sheet_schema",
    "Selected worksheets must have identical headings.": "sheet_schema",
    "Excel tables must have identical headings in the same order.": "table_schema",
    "Excel tables must have identical headings.": "table_schema",
    "Excel output must have an .xlsx filename.": "output_format",
    "Mapping must be a private regular file owned by this user (mode 0600).": (
        "bundle_permissions"
    ),
    "Private mapping storage requires supported POSIX permissions.": "bundle_permissions",
    "Windows private storage permissions could not be verified.": "bundle_permissions",
    "Windows storage requires a local fixed NTFS path without reparse points.": (
        "storage_location"
    ),
    "Only .docx Word documents are supported.": "document_invalid",
    "Input is not a supported Word document.": "document_invalid",
    "Word document has an unsafe archive structure.": "document_invalid",
    "Word document contains malformed XML.": "document_invalid",
    "Word document exceeds supported archive limits.": "document_limit",
    "Protected Word document exceeds the supported size limit.": "document_limit",
    "Word document contains tracked changes that must be resolved first.": "document_tracked_changes",
    "Word document contains hidden text that must be resolved first.": "document_hidden_text",
    "Word document contains unsupported embedded or active content.": "document_active_content",
    "Word document comments require explicit removal before protection.": "document_comments",
    "A document identifier is split across formatted runs and cannot be protected safely.": "document_split_identifier",
    "A document identifier remained after protection.": "document_protection_incomplete",
    "Returned Word document does not preserve every protection token.": "document_token_integrity",
    "Returned Word document contains an original protected identifier.": "document_original_identifier",
    "Returned Word document contains tracked changes.": "document_tracked_changes",
    "Returned Word document contains hidden text.": "document_hidden_text",
    "Returned Word document contains unsupported embedded or active content.": "document_active_content",
    "Document restoration bundle version or structure is unsupported.": "bundle_incompatible",
    "Document restoration bundle version or envelope is unsupported.": "bundle_incompatible",
    "Document restoration bundle could not be authenticated or decoded.": "bundle_authentication",
    "Unable to access private document restoration bundle.": "bundle_unavailable",
    "Word document changed after protection review.": "stale_review",
    "Word document changed after restoration review.": "stale_review",
    "Private document bundle must have an .enc filename.": "output_format",
}


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("constant")


def _string(value: object, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("string")
    return value


def _path(value: object, *, optional: bool = False) -> Path | None:
    item = _string(value, optional=optional)
    return None if item is None else Path(item)


def _payload(value: object, required: set[str], optional: set[str] = frozenset()) -> dict:
    if (
        not isinstance(value, dict)
        or not required <= set(value)
        or set(value) - required - optional
    ):
        raise ValueError("payload")
    return value


def _sheet(value: object) -> str | None:
    return _string(value, optional=True)


def _sheet_selection(value: object) -> str | tuple[str, ...] | None:
    return _sheets(value) if isinstance(value, list) else _sheet(value)


def _drafts(value: object) -> dict[str, RuleDraft]:
    if not isinstance(value, dict) or not 1 <= len(value) <= 128:
        raise ValueError("drafts")
    result = {}
    for name, raw in value.items():
        if (
            not isinstance(name, str)
            or not isinstance(raw, dict)
            or set(raw)
            != {
                "action",
                "classification",
                "allowed_values",
                "bins",
                "bounds",
            }
        ):
            raise ValueError("draft")
        if not isinstance(raw["action"], str) or not isinstance(raw["classification"], str):
            raise ValueError("draft")
        if not isinstance(raw["allowed_values"], list) or not isinstance(raw["bins"], list):
            raise ValueError("draft")
        if any(not isinstance(item, str) for item in raw["allowed_values"]):
            raise ValueError("draft")
        if any(not isinstance(pair, list) or len(pair) != 2 for pair in raw["bins"]):
            raise ValueError("draft")
        bounds = raw["bounds"]
        if bounds is not None and (not isinstance(bounds, list) or len(bounds) != 2):
            raise ValueError("draft")
        result[name] = RuleDraft(
            raw["action"],
            raw["classification"],
            tuple(raw["allowed_values"]),
            tuple(tuple(pair) for pair in raw["bins"]),
            tuple(bounds) if bounds is not None else None,
            None,
        )
    return result


def _draft_dict(draft: RuleDraft) -> dict:
    return {
        "action": draft.action,
        "classification": draft.classification,
        "allowed_values": list(draft.allowed_values),
        "bins": [list(pair) for pair in draft.bins],
        "bounds": list(draft.bounds) if draft.bounds is not None else None,
    }


def _columns(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or len(value) > 128
        or any(not isinstance(item, str) or len(item) > 64 for item in value)
    ):
        raise ValueError("columns")
    return tuple(value)


def _sheets(value: object) -> tuple[str, ...]:
    result = _columns(value)
    if not result or len(result) != len(set(result)):
        raise ValueError("sheets")
    return result


def _relational_drafts(value: object) -> dict[str, dict[str, RuleDraft]]:
    if (
        not isinstance(value, dict)
        or not 1 <= len(value) <= 128
        or any(not isinstance(name, str) for name in value)
    ):
        raise ValueError("relational drafts")
    return {name: _drafts(raw) for name, raw in value.items()}


def _approved_results(value: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict) or not value or any(not isinstance(name, str) for name in value):
        raise ValueError("approved results")
    return {name: _columns(columns) for name, columns in value.items()}


def _document_terms(value: object) -> tuple[DocumentTerm, ...]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("document terms")
    result = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"value", "kind"}
            or not isinstance(item["value"], str)
            or not isinstance(item["kind"], str)
        ):
            raise ValueError("document term")
        result.append(DocumentTerm(item["value"], item["kind"]))
    return tuple(result)


class Bridge:
    """A single in-memory review is valid until the next operation or approval."""

    def __init__(self) -> None:
        self.pending: tuple[str, str, object] | None = None

    def dispatch(self, command: str, raw: object) -> dict:
        if command == "hello":
            _payload(raw, set())
            return {
                "protocol": PROTOCOL_VERSION,
                "artefacts": ["workbook", "document"],
                "desktop_contract": "shared",
            }
        if command in {"approve_document_protection", "approve_document_restoration"}:
            required = {"review_id", "passphrase"} if command == "approve_document_protection" else {"review_id"}
            data = _payload(raw, required)
            token = _string(data["review_id"])
            pending = self.pending
            self.pending = None
            if pending is None or pending[0] != command or pending[1] != token:
                raise SafetyError("Review is stale; prepare and review again.")
            if command == "approve_document_protection":
                approve_document_protection(
                    pending[2], _string(data["passphrase"]), approved=True
                )
            else:
                approve_document_restoration(pending[2], authorised=True)
            return {"created": True}
        if command in {
            "approve_protection",
            "approve_relational_protection",
            "approve_reconstruction",
            "approve_relational_reconstruction",
            "approve_export",
        }:
            data = _payload(
                raw, {"review_id"}, {"passphrase", "approved_results", "approved_sheets"}
            )
            token = _string(data["review_id"])
            pending = self.pending
            self.pending = None
            if pending is None or pending[0] != command or pending[1] != token:
                raise SafetyError("Review is stale; prepare and review again.")
            review = pending[2]
            if command == "approve_protection":
                _payload(data, {"review_id", "passphrase"})
                approve_protection(review, _string(data["passphrase"]), approved=True)
                return {"created": True}
            if command == "approve_relational_protection":
                _payload(data, {"review_id", "passphrase"})
                approve_relational_protection(review, _string(data["passphrase"]), approved=True)
                return {"created": True}
            if command == "approve_export":
                _payload(data, {"review_id", "passphrase"})
                approve_export(review, _string(data["passphrase"]), approved=True)
                return {"created": True}
            _payload(data, {"review_id", "approved_results"}, {"approved_sheets"})
            approved_sheets = _columns(data.get("approved_sheets", []))
            if command == "approve_relational_reconstruction":
                rows = approve_relational_reconstruction(
                    review,
                    _approved_results(data["approved_results"]),
                    approved_sheets,
                    authorised=True,
                )
                return {"created": True, "rows": rows}
            rows = approve_reconstruction(
                review,
                _columns(data["approved_results"]),
                approved_sheets,
                authorised=True,
            )
            return {"created": True, "rows": rows}
        self.pending = None
        if command == "cancel":
            _payload(raw, set())
            return {"cancelled": True}
        if command == "inspect_document":
            data = _payload(raw, {"source"})
            return inspect_document(_path(data["source"])).summary()
        if command == "prepare_document_protection":
            data = _payload(
                raw,
                {"source", "output", "terms", "remove_comments"},
                {"bundle"},
            )
            if type(data["remove_comments"]) is not bool:
                raise ValueError("remove comments")
            review = prepare_document_protection(
                _path(data["source"]),
                _document_terms(data["terms"]),
                _path(data["output"]),
                _path(data.get("bundle"), optional=True),
                remove_comments=data["remove_comments"],
            )
            token = new_id()
            self.pending = ("approve_document_protection", token, review)
            return {
                "review_id": token,
                "replacement_count": review.replacement_count,
                "replacement_occurrences": review.replacement_occurrences,
                "comments_removed": review.comments_removed,
                "inspection": review.inspection.summary(),
                "output": str(review.output),
                "bundle": str(review.bundle_path),
            }
        if command == "prepare_document_restoration":
            data = _payload(raw, {"returned", "bundle", "output", "passphrase"})
            review = prepare_document_restoration(
                _path(data["returned"]),
                _path(data["bundle"]),
                _path(data["output"]),
                _string(data["passphrase"]),
            )
            token = new_id()
            self.pending = ("approve_document_restoration", token, review)
            return {
                "review_id": token,
                "replacement_count": review.replacement_count,
                "replacement_occurrences": review.replacement_occurrences,
                "output": str(review.output),
            }
        if command == "list_sheets":
            data = _payload(raw, {"path"})
            return {"sheets": list(list_excel_sheets(_path(data["path"])))}
        if command == "inspect":
            data = _payload(raw, {"source", "sheet"})
            return inspect_source(_path(data["source"]), _sheet(data["sheet"]))
        if command == "locate_unsafe_source_cells":
            data = _payload(raw, {"source", "bundle", "passphrase", "relational", "sheet"})
            if type(data["relational"]) is not bool:
                raise ValueError("relational")
            return locate_unsafe_source_cells(
                _path(data["source"]),
                _path(data["bundle"]),
                _string(data["passphrase"]),
                relational=data["relational"],
                sheet=_sheet_selection(data["sheet"]),
            )
        if command == "categories":
            data = _payload(raw, {"source", "sheet", "column"})
            review = local_category_review(
                _path(data["source"]), _string(data["column"]), _sheet(data["sheet"])
            )
            return {
                "values": list(review.values),
                "blank_count": review.blank_count,
            }
        if command == "load_policy":
            data = _payload(raw, {"source", "sheet", "policy"})
            drafts, threshold = load_drafts(
                _path(data["source"]), _path(data["policy"]), _sheet(data["sheet"])
            )
            return {
                "drafts": {name: _draft_dict(d) for name, d in drafts.items()},
                "threshold": threshold,
            }
        if command == "save_policy":
            data = _payload(raw, {"source", "sheet", "destination", "drafts", "threshold"})
            saved = save_policy(
                _path(data["source"]),
                _path(data["destination"]),
                _drafts(data["drafts"]),
                _string(data["threshold"]),
                _sheet(data["sheet"]),
            )
            return {"saved": str(saved)}
        if command == "prepare_protection":
            data = _payload(
                raw,
                {"source", "sheet", "output", "drafts", "threshold"},
                {"bundle", "validation_profile"},
            )
            review = prepare_protection(
                _path(data["source"]),
                _drafts(data["drafts"]),
                _string(data["threshold"]),
                _path(data["output"]),
                _path(data.get("bundle"), optional=True),
                _sheet(data["sheet"]),
                _string(data.get("validation_profile", "strict")),
            )
            token = new_id()
            self.pending = ("approve_protection", token, review)
            return {
                "review_id": token,
                "rows": review.source_rows,
                "removed": review.removed_fields,
                "obfuscated": review.obfuscated_fields,
                "retained": review.retained_fields,
                "output": str(review.output),
                "bundle": str(review.bundle_path),
                "validation": review.validation.summary(),
            }
        if command == "prepare_relational_protection":
            data = _payload(
                raw,
                {"source", "sheets", "output", "drafts", "threshold", "validation_profile"},
                {"bundle", "shared_code_fields"},
            )
            review = prepare_relational_protection(
                _path(data["source"]),
                _sheets(data["sheets"]),
                _relational_drafts(data["drafts"]),
                _string(data["threshold"]),
                _path(data["output"]),
                _path(data.get("bundle"), optional=True),
                _string(data["validation_profile"]),
                _columns(data.get("shared_code_fields", [])),
            )
            token = new_id()
            self.pending = ("approve_relational_protection", token, review)
            return {
                "review_id": token,
                "rows": sum(len(table.rows) for table in review.source_tables.values()),
                "worksheets": len(review.sheets),
                "entities": len(review.candidate.entities),
                "shared_code_fields": list(review.candidate.shared_code_fields),
                "output": str(review.output),
                "bundle": str(review.bundle_path),
                "validation": review.validation.summary(),
            }
        if command == "prepare_reconstruction":
            data = _payload(
                raw,
                {
                    "returned",
                    "source",
                    "bundle",
                    "output",
                    "passphrase",
                    "returned_sheet",
                    "source_sheet",
                },
            )
            review = prepare_reconstruction(
                _path(data["returned"]),
                _path(data["source"]),
                _path(data["bundle"]),
                _path(data["output"]),
                _string(data["passphrase"]),
                returned_sheet=_sheet_selection(data["returned_sheet"]),
                source_sheet=_sheet_selection(data["source_sheet"]),
            )
            token = new_id()
            self.pending = ("approve_reconstruction", token, review)
            return {
                "review_id": token,
                "rows": len(review.returned_table.rows),
                "new_columns": list(review.new_columns),
                "new_sheets": list(review.analysis_sheets),
                "source_columns": list(review.source_table.columns),
                "coded_columns": list(review.bundle["codebooks"]),
                "output": str(review.output),
            }
        if command == "prepare_relational_reconstruction":
            data = _payload(
                raw,
                {"returned", "source", "bundle", "output", "passphrase"},
            )
            review = prepare_relational_reconstruction(
                _path(data["returned"]),
                _path(data["source"]),
                _path(data["bundle"]),
                _path(data["output"]),
                _string(data["passphrase"]),
            )
            token = new_id()
            self.pending = ("approve_relational_reconstruction", token, review)
            return {
                "review_id": token,
                "rows": sum(len(table.rows) for table in review.returned_tables.values()),
                "new_columns": {
                    sheet: list(columns) for sheet, columns in review.new_columns.items()
                },
                "new_sheets": list(review.analysis_sheets),
                "output": str(review.output),
            }
        if command == "prepare_export":
            data = _payload(raw, {"source", "sheet", "policy", "output"}, {"map"})
            review = prepare_export(
                _path(data["source"]),
                _path(data["policy"]),
                _path(data["output"]),
                _path(data.get("map"), optional=True),
                _sheet(data["sheet"]),
            )
            token = new_id()
            self.pending = ("approve_export", token, review)
            return {
                "review_id": token,
                "rows": review.source_rows,
                "output": str(review.output),
                "map": str(review.map_path),
                "validation": review.validation.summary(),
            }
        if command == "inspect_returned":
            data = _payload(raw, {"path", "sheet"})
            review = inspect_returned(_path(data["path"]), _sheet(data["sheet"]))
            return {"rows": review.rows, "result_columns": list(review.result_columns)}
        if command == "restore_results":
            data = _payload(
                raw,
                {
                    "returned",
                    "sheet",
                    "map",
                    "output",
                    "results",
                    "passphrase",
                    "source",
                    "policy",
                    "source_sheet",
                },
            )
            rows = restore_results(
                _path(data["returned"]),
                _path(data["map"]),
                _path(data["output"]),
                _columns(data["results"]),
                _string(data["passphrase"]),
                authorised=True,
                sheet=_sheet(data["sheet"]),
                coded_source=_path(data["source"], optional=True),
                coded_policy=_path(data["policy"], optional=True),
                coded_source_sheet=_sheet(data["source_sheet"]),
            )
            return {"created": True, "rows": rows}
        raise ValueError("command")

    def process_line(self, line: bytes) -> bytes:
        request_id = ""
        try:
            if len(line) > MAX_REQUEST or not line.endswith(b"\n"):
                raise ValueError("frame")
            request = json.loads(
                line.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_reject_constant
            )
            if (
                not isinstance(request, dict)
                or set(request) != {"version", "id", "command", "payload"}
                or type(request["version"]) is not int
                or request["version"] != PROTOCOL_VERSION
            ):
                raise ValueError("request")
            request_id = _string(request["id"])
            command = _string(request["command"])
            result = self.dispatch(command, request["payload"])
            response = {"version": PROTOCOL_VERSION, "id": request_id, "ok": True, "result": result}
        except SafetyError as error:
            self.pending = None
            response = {
                "version": PROTOCOL_VERSION,
                "id": request_id,
                "ok": False,
                "error": PUBLIC_SAFETY_ERRORS.get(str(error), "safety_rejected"),
            }
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
            self.pending = None
            response = {
                "version": PROTOCOL_VERSION,
                "id": request_id,
                "ok": False,
                "error": "invalid_request",
            }
        except OSError:
            self.pending = None
            response = {
                "version": PROTOCOL_VERSION,
                "id": request_id,
                "ok": False,
                "error": "local_io_failure",
            }
        encoded = json.dumps(response, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_RESPONSE:
            encoded = b'{"version":1,"id":"","ok":false,"error":"response_limit"}'
        return encoded + b"\n"


def main() -> None:
    bridge = Bridge()
    while True:
        line = sys.stdin.buffer.readline(MAX_REQUEST + 2)
        if not line:
            return
        sys.stdout.buffer.write(bridge.process_line(line))
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
