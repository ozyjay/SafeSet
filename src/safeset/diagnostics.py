"""Private, value-free local diagnostic events."""

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from .errors import SafetyError
from .storage import outside_repositories

MAX_LOG_BYTES = 1024 * 1024
STAGES = frozenset(
    {
        "cli.inspect",
        "cli.sanitise",
        "cli.validate",
        "cli.restore",
        "cli.log_path",
        "desktop.app",
        "desktop.inspect",
        "desktop.policy.columns",
        "desktop.policy.choices",
        "desktop.policy.save",
        "desktop.export.prepare",
        "desktop.export.approve",
        "desktop.restore.review",
        "desktop.restore.publish",
    }
)
EVENTS = frozenset(
    {
        "start",
        "source_read",
        "policy_loaded",
        "candidate_ready",
        "validation_passed",
        "approval_received",
        "map_unlocked",
        "published",
        "success",
        "rejected",
        "io_error",
        "declined",
        "closed",
    }
)
REASON_CODES = {
    "Input must be a regular local file.": "input_type",
    "Unable to read the requested local file.": "input_unavailable",
    "Input exceeds the supported size limit.": "size_limit",
    "Excel workbook exceeds supported archive limits.": "size_limit",
    "Excel workbook has an unsafe archive structure.": "archive_invalid",
    "Excel workbook contains unsupported active content.": "active_content",
    "Input is not a supported Excel workbook.": "workbook_invalid",
    "Only .xlsx Excel workbooks are supported.": "input_type",
    "Excel workbook contains external links.": "active_content",
    "Excel workbook has no visible worksheet.": "sheet_selection",
    "Select one or more worksheets from the Excel workbook.": "sheet_selection",
    "Worksheet selection is invalid.": "sheet_selection",
    "Selected worksheet is missing, hidden or repeated.": "sheet_selection",
    "Selected worksheets must have identical headings in the same order.": "sheet_schema",
    "Selected worksheets exceed the combined row limit.": "row_limit",
    "Excel tables must have identical headings in the same order.": "table_schema",
    "Excel table headings differ from its metadata.": "table_schema",
    "Excel table has unsupported structure.": "table_structure",
    "Excel table has unsupported dimensions.": "table_structure",
    "Excel worksheet exceeds the supported table count.": "table_structure",
    "Excel tables overlap.": "table_structure",
    "Excel table has unsupported totals metadata.": "table_structure",
    "Excel tables exceed the combined row limit.": "row_limit",
    "Excel worksheet exceeds the supported row limit.": "row_limit",
    "Excel worksheet exceeds the supported column limit.": "column_limit",
    "Excel data range contains merged cells.": "merged_cells",
    "Excel data range contains hidden rows.": "hidden_data",
    "Excel data range contains hidden columns.": "hidden_data",
    "Excel headings are missing, duplicated or malformed.": "heading_invalid",
    "Excel workbook contains unsupported cell features.": "cell_features",
    "Excel workbook contains an unsupported cell type.": "cell_type",
    "Excel row shape or field size is invalid.": "row_shape",
    "Excel output must have an .xlsx filename.": "output_format",
    "Source schema differs from policy; missing or unexpected columns.": "policy_schema",
    "Source keys must be non-empty and unique.": "source_keys",
    "Validation failed; no export is permitted.": "validation",
    "Mapping and export must use separate storage directories.": "destination_separation",
    "Destination already exists; overwriting is prohibited.": "destination_exists",
    "Mapping structure is invalid.": "mapping_invalid",
    "Mapping records are malformed or ambiguous.": "mapping_invalid",
}
EVENTS = EVENTS | frozenset(REASON_CODES.values())


def log_path() -> Path:
    return Path.home() / ".local" / "state" / "safeset" / "diagnostics.log"


def record_reason(stage: str, error: SafetyError) -> None:
    """Map an exact fixed error message to a safe code; discard all other text."""
    code = REASON_CODES.get(str(error))
    if code is not None:
        record(stage, code)


def record(stage: str, event: str) -> bool:
    """Append only allowlisted codes; never accept filenames or error text."""
    if stage not in STAGES or event not in EVENTS or os.name != "posix":
        return False
    descriptor = None
    try:
        path = log_path()
        directory = path.parent
        if directory.is_symlink() or directory.resolve() != directory.absolute():
            return False
        outside_repositories(path)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory_info = directory.stat()
        if (
            not stat.S_ISDIR(directory_info.st_mode)
            or directory_info.st_uid != os.getuid()
            or stat.S_IMODE(directory_info.st_mode) != 0o700
        ):
            return False
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            return False
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{timestamp} {stage} {event}\n".encode("ascii")
        if os.fstat(descriptor).st_size + len(line) > MAX_LOG_BYTES:
            os.ftruncate(descriptor, 0)
        os.write(descriptor, line)
        return True
    except (OSError, ValueError, SafetyError):
        return False
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
