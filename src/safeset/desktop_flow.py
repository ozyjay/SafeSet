"""Local desktop workflow state; no UI toolkit or network dependencies."""

from dataclasses import dataclass
from pathlib import Path

from .classification import inspect_table
from .errors import SafetyError
from .ingestion import excel_bytes, read_excel, require_excel_path
from .mapping import read_mapping
from .policy import NAME, Policy, load_policy
from .pseudonyms import valid_id
from .restoration import restore
from .storage import default_map_path, map_destination, output_destination, publish
from .transform import Candidate, sanitise
from .validation import ValidationReport, validate
from .workflow import export_candidate


@dataclass(frozen=True)
class ExportReview:
    source: Path
    output: Path
    map_path: Path
    policy: Policy
    candidate: Candidate
    validation: ValidationReport
    source_rows: int
    source_columns: int
    dropped_columns: int


@dataclass(frozen=True)
class ReturnedReview:
    path: Path
    rows: int
    result_columns: tuple[str, ...]


def inspect_source(source: Path) -> dict:
    """Return aggregate characteristics only; the UI does not show cell samples."""
    return inspect_table(read_excel(source))


def inspect_returned(path: Path) -> ReturnedReview:
    """Read returned headings and ID shape without exposing cell values to the UI."""
    table = read_excel(path)
    if "record_id" not in table.columns or len(table.columns) < 2:
        raise SafetyError("Returned Excel workbook needs record_id and at least one result column.")
    if any(not NAME.fullmatch(name) for name in table.columns if name != "record_id"):
        raise SafetyError("Result headings must use lowercase snake_case, such as team.")
    ids = [row["record_id"] for row in table.rows]
    if not ids or any(not valid_id(value) for value in ids) or len(set(ids)) != len(ids):
        raise SafetyError("Returned IDs are malformed or duplicated.")
    return ReturnedReview(
        path, len(table.rows), tuple(c for c in table.columns if c != "record_id")
    )


def prepare_export(
    source: Path, policy_path: Path, output: Path, map_path: Path | None
) -> ExportReview:
    """Prepare and validate a candidate without publishing either artefact."""
    policy = load_policy(policy_path)
    table = read_excel(source)
    candidate = sanitise(table, policy)
    validation = validate(candidate.table, policy)
    require_excel_path(output)
    destination = output_destination(output, source)
    mapping = map_destination(map_path or default_map_path(), destination, source)
    return ExportReview(
        source,
        destination,
        mapping,
        policy,
        candidate,
        validation,
        len(table.rows),
        len(table.columns),
        sum(rule.action == "drop" for rule in policy.columns.values()),
    )


def approve_export(review: ExportReview, passphrase: str, *, approved: bool) -> None:
    """Use the reviewed in-memory candidate; domain workflow revalidates at publication."""
    if not approved:
        raise SafetyError("Explicit export approval is required.")
    review.validation.require_pass()
    export_candidate(
        review.candidate,
        review.policy,
        review.output,
        review.map_path,
        passphrase,
        approved=True,
        create_map=True,
        source_path=review.source,
    )


def restore_results(
    analysed_path: Path,
    map_path: Path,
    output: Path,
    result_columns: tuple[str, ...],
    passphrase: str,
    *,
    authorised: bool,
) -> int:
    """Restore exact IDs after a separate, explicit local authorisation."""
    if not authorised:
        raise SafetyError("Explicit restoration authorisation is required.")
    require_excel_path(output)
    destination = output_destination(output, analysed_path, map_path)
    analysed = read_excel(analysed_path)
    mapping = read_mapping(map_path, passphrase, analysed_path, output)
    restored = restore(analysed, mapping, result_columns)
    publish(destination, excel_bytes(restored))
    return len(restored.rows)
