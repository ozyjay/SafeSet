"""Local desktop workflow state; no UI toolkit or network dependencies."""

from dataclasses import dataclass
from pathlib import Path

from .bundle import read_bundle
from .classification import inspect_table
from .errors import SafetyError
from .ingestion import excel_bytes, read_excel, require_excel_path, valid_heading
from .mapping import read_mapping
from .policy import Policy, load_policy, parse_policy
from .policy_authoring import RuleDraft, policy_payload
from .pseudonyms import valid_id
from .reconstruction import reconstruct, review_reconstruction
from .restoration import restore
from .storage import default_map_path, map_destination, output_destination, publish
from .transform import Candidate, sanitise
from .validation import ValidationReport, validate
from .workflow import export_candidate, protect_candidate


@dataclass(frozen=True)
class ExportReview:
    source: Path
    sheet: str | tuple[str, ...] | None
    output: Path
    map_path: Path
    policy: Policy
    candidate: Candidate
    validation: ValidationReport
    source_rows: int
    source_columns: int
    dropped_columns: int
    formula_cells: int
    date_cells: int


@dataclass(frozen=True)
class ReturnedReview:
    path: Path
    sheet: str | tuple[str, ...] | None
    rows: int
    result_columns: tuple[str, ...]


@dataclass(frozen=True)
class ProtectionReview:
    source: Path
    sheet: str | tuple[str, ...] | None
    output: Path
    bundle_path: Path
    source_table: object
    policy: Policy
    candidate: Candidate
    validation: ValidationReport
    source_rows: int
    removed_fields: int
    obfuscated_fields: int
    retained_fields: int


@dataclass(frozen=True)
class ReconstructionReview:
    source_path: Path
    returned_path: Path
    bundle_path: Path
    output: Path
    source_table: object
    returned_table: object
    bundle: dict
    new_columns: tuple[str, ...]
    source_sheet: str | tuple[str, ...] | None
    returned_sheet: str | tuple[str, ...] | None


def prepare_protection(
    source: Path,
    drafts: dict[str, RuleDraft],
    threshold: str,
    output: Path,
    bundle_path: Path | None = None,
    sheet: str | tuple[str, ...] | None = None,
) -> ProtectionReview:
    table = read_excel(source, sheet, allow_cached_formulas=True, allow_source_dates=True)
    if set(table.columns) != set(drafts):
        raise SafetyError("Every source field needs an explicit protection decision.")
    policy = parse_policy(policy_payload(drafts, threshold))
    candidate = sanitise(table, policy)
    validation = validate(candidate.table, policy)
    require_excel_path(output)
    destination = output_destination(output, source)
    bundle_destination = map_destination(bundle_path or default_map_path(), destination, source)
    return ProtectionReview(
        source,
        sheet,
        destination,
        bundle_destination,
        table,
        policy,
        candidate,
        validation,
        len(table.rows),
        sum(rule.action == "drop" for rule in policy.columns.values()),
        sum(rule.action == "code" for rule in policy.columns.values()),
        sum(rule.action in {"keep", "keep_numeric", "bin"} for rule in policy.columns.values()),
    )


def approve_protection(review: ProtectionReview, passphrase: str, *, approved: bool) -> None:
    review.validation.require_pass()
    protect_candidate(
        review.source_table,
        review.candidate,
        review.policy,
        review.output,
        review.bundle_path,
        passphrase,
        approved=approved,
        source_path=review.source,
        sheet=review.sheet,
    )


def prepare_reconstruction(
    returned_path: Path,
    source_path: Path,
    bundle_path: Path,
    output: Path,
    passphrase: str,
    *,
    returned_sheet: str | tuple[str, ...] | None = None,
    source_sheet: str | tuple[str, ...] | None = None,
) -> ReconstructionReview:
    require_excel_path(output)
    destination = output_destination(output, returned_path, source_path, bundle_path)
    bundle = read_bundle(bundle_path, passphrase, returned_path, source_path, output)
    source = read_excel(
        source_path, source_sheet, allow_cached_formulas=True, allow_source_dates=True
    )
    returned = read_excel(returned_path, returned_sheet)
    new_columns = review_reconstruction(source, returned, bundle)
    return ReconstructionReview(
        source_path,
        returned_path,
        bundle_path,
        destination,
        source,
        returned,
        bundle,
        new_columns,
        source_sheet,
        returned_sheet,
    )


def approve_reconstruction(
    review: ReconstructionReview,
    approved_results: tuple[str, ...],
    *,
    authorised: bool,
) -> int:
    if not authorised:
        raise SafetyError("Explicit restoration authorisation is required.")
    # Re-read both untrusted workbooks before publication so review cannot go stale.
    current_source = read_excel(
        review.source_path, review.source_sheet, allow_cached_formulas=True, allow_source_dates=True
    )
    current_returned = read_excel(review.returned_path, review.returned_sheet)
    if current_source != review.source_table or current_returned != review.returned_table:
        raise SafetyError("A workbook changed after restoration review.")
    restored = reconstruct(current_source, current_returned, review.bundle, approved_results)
    destination = output_destination(
        review.output, review.returned_path, review.source_path, review.bundle_path
    )
    publish(destination, excel_bytes(restored))
    return len(restored.rows)


def inspect_source(source: Path, sheet: str | tuple[str, ...] | None = None) -> dict:
    """Return aggregate characteristics only; the UI does not show cell samples."""
    return inspect_table(
        read_excel(source, sheet, allow_cached_formulas=True, allow_source_dates=True)
    )


def inspect_returned(path: Path, sheet: str | tuple[str, ...] | None = None) -> ReturnedReview:
    """Read returned headings and ID shape without exposing cell values to the UI."""
    table = read_excel(path, sheet)
    if "record_id" not in table.columns or len(table.columns) < 2:
        raise SafetyError("Returned Excel workbook needs record_id and at least one result column.")
    if any(not valid_heading(name) for name in table.columns if name != "record_id"):
        raise SafetyError("Result headings contain unsupported text.")
    ids = [row["record_id"] for row in table.rows]
    if not ids or any(not valid_id(value) for value in ids) or len(set(ids)) != len(ids):
        raise SafetyError("Returned IDs are malformed or duplicated.")
    return ReturnedReview(
        path, sheet, len(table.rows), tuple(c for c in table.columns if c != "record_id")
    )


def prepare_export(
    source: Path,
    policy_path: Path,
    output: Path,
    map_path: Path | None,
    sheet: str | tuple[str, ...] | None = None,
) -> ExportReview:
    """Prepare and validate a candidate without publishing either artefact."""
    policy = load_policy(policy_path)
    table = read_excel(source, sheet, allow_cached_formulas=True, allow_source_dates=True)
    candidate = sanitise(table, policy)
    validation = validate(candidate.table, policy)
    require_excel_path(output)
    destination = output_destination(output, source)
    mapping = map_destination(map_path or default_map_path(), destination, source)
    return ExportReview(
        source,
        sheet,
        destination,
        mapping,
        policy,
        candidate,
        validation,
        len(table.rows),
        len(table.columns),
        sum(rule.action == "drop" for rule in policy.columns.values()),
        table.formula_cells,
        table.date_cells,
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
    sheet: str | tuple[str, ...] | None = None,
    coded_source: Path | None = None,
    coded_policy: Path | None = None,
    coded_source_sheet: str | tuple[str, ...] | None = None,
) -> int:
    """Restore exact IDs after a separate, explicit local authorisation."""
    if not authorised:
        raise SafetyError("Explicit restoration authorisation is required.")
    if (coded_source is None) != (coded_policy is None):
        raise SafetyError("Restoring coded labels requires both the original source and policy.")
    require_excel_path(output)
    if coded_source is not None:
        require_excel_path(coded_source)
    destination = output_destination(
        output, analysed_path, map_path, *(p for p in (coded_source, coded_policy) if p)
    )
    analysed = read_excel(analysed_path, sheet)
    mapping = read_mapping(
        map_path, passphrase, analysed_path, output, *(p for p in (coded_source, coded_policy) if p)
    )
    source_table = (
        read_excel(
            coded_source, coded_source_sheet, allow_cached_formulas=True, allow_source_dates=True
        )
        if coded_source is not None
        else None
    )
    policy = load_policy(coded_policy) if coded_policy is not None else None
    restored = restore(
        analysed, mapping, result_columns, coded_source=source_table, coded_policy=policy
    )
    publish(destination, excel_bytes(restored))
    return len(restored.rows)
