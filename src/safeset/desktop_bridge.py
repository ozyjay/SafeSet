"""Bounded local JSON-line bridge for the macOS desktop. Never log requests."""

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
    prepare_export,
    prepare_protection,
    prepare_reconstruction,
    prepare_relational_protection,
    prepare_relational_reconstruction,
    restore_results,
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


class Bridge:
    """A single in-memory review is valid until the next operation or approval."""

    def __init__(self) -> None:
        self.pending: tuple[str, str, object] | None = None

    def dispatch(self, command: str, raw: object) -> dict:
        if command == "hello":
            _payload(raw, set())
            return {"protocol": PROTOCOL_VERSION}
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
        if command == "list_sheets":
            data = _payload(raw, {"path"})
            return {"sheets": list(list_excel_sheets(_path(data["path"])))}
        if command == "inspect":
            data = _payload(raw, {"source", "sheet"})
            return inspect_source(_path(data["source"]), _sheet(data["sheet"]))
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
