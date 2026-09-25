"""Local desktop workflow state; no UI toolkit or network dependencies."""

from dataclasses import dataclass
from pathlib import Path

from .bundle import read_bundle, source_digest
from .classification import has_control, inspect_table
from .errors import SafetyError
from .ingestion import (
    excel_bytes,
    excel_workbook_bytes,
    list_excel_sheets,
    read_excel,
    read_excel_sheets,
    require_excel_path,
    valid_heading,
)
from .mapping import read_mapping
from .policy import Policy, load_policy, parse_policy
from .policy_authoring import RuleDraft, policy_payload
from .pseudonyms import valid_id
from .reconstruction import (
    approved_analysis_sheets,
    reconstruct,
    review_analysis_sheets,
    review_reconstruction,
)
from .relational import (
    RelationalCandidate,
    RelationalValidation,
    publish_relational_candidate,
    read_relational_bundle,
    reconstruct_relational,
    relational_changes,
    review_relational_reconstruction,
    sanitise_relational,
    validate_relational,
    workbook_digest,
)
from .restoration import restore
from .storage import default_map_path, map_destination, output_destination, publish
from .transform import Candidate, sanitise
from .validation import ValidationReport, validate
from .workbook_editing import (
    file_digest,
    patched_workbook_bytes,
    validate_editable_fields,
    validate_editable_layout,
)
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
    validation_profile: str


@dataclass(frozen=True)
class ReconstructionReview:
    source_path: Path
    returned_path: Path
    bundle_path: Path
    output: Path
    source_table: object
    returned_table: object
    analysis_sheets: dict[str, object]
    bundle: dict
    new_columns: tuple[str, ...]
    restored_sheet_name: str
    returned_bound_sheets: tuple[str, ...]
    source_sheet: str | tuple[str, ...] | None
    returned_sheet: str | tuple[str, ...] | None


@dataclass(frozen=True)
class RelationalProtectionReview:
    source: Path
    sheets: tuple[str, ...]
    output: Path
    bundle_path: Path
    source_tables: dict[str, object]
    policies: dict[str, Policy]
    candidate: RelationalCandidate
    validation: RelationalValidation
    editable_fields: dict | None = None
    source_file_digest: str | None = None


@dataclass(frozen=True)
class RelationalReconstructionReview:
    source_path: Path
    returned_path: Path
    bundle_path: Path
    output: Path
    source_tables: dict[str, object]
    returned_tables: dict[str, object]
    analysis_sheets: dict[str, object]
    bundle: dict
    new_columns: dict[str, tuple[str, ...]]
    visible_returned_sheets: tuple[str, ...]
    changes: dict | None = None
    workbook_bytes: bytes | None = None


def prepare_protection(
    source: Path,
    drafts: dict[str, RuleDraft],
    threshold: str,
    output: Path,
    bundle_path: Path | None = None,
    sheet: str | tuple[str, ...] | None = None,
    validation_profile: str = "strict",
) -> ProtectionReview:
    table = read_excel(source, sheet, allow_cached_formulas=True, allow_source_dates=True)
    if set(table.columns) != set(drafts):
        raise SafetyError("Every source field needs an explicit protection decision.")
    policy = parse_policy(policy_payload(drafts, threshold))
    candidate = sanitise(table, policy)
    validation = validate(candidate.table, policy, validation_profile)
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
        validation_profile,
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
        validation_profile=review.validation_profile,
    )


def prepare_relational_protection(
    source: Path,
    sheets: tuple[str, ...],
    drafts: dict[str, dict[str, RuleDraft]],
    threshold: str,
    output: Path,
    bundle_path: Path | None = None,
    validation_profile: str = "strict",
    shared_code_fields: tuple[str, ...] = (),
    editable_fields: dict | None = None,
) -> RelationalProtectionReview:
    if set(sheets) != set(drafts):
        raise SafetyError("Every selected worksheet needs explicit field decisions.")
    digest = file_digest(source) if editable_fields is not None else None
    sources = read_excel_sheets(source, sheets, allow_cached_formulas=True, allow_source_dates=True)
    policies = {}
    for sheet in sheets:
        if set(sources[sheet].columns) != set(drafts[sheet]):
            raise SafetyError("Every source field needs an explicit protection decision.")
        policies[sheet] = parse_policy(policy_payload(drafts[sheet], threshold))
    if editable_fields is not None:
        validate_editable_fields(editable_fields, policies)
        validate_editable_layout(source, editable_fields)
        if file_digest(source) != digest:
            raise SafetyError("Source workbook changed after relational protection review.")
    candidate = sanitise_relational(sources, policies, shared_code_fields)
    validation = validate_relational(candidate, policies, validation_profile)
    require_excel_path(output)
    destination = output_destination(output, source)
    private_bundle = map_destination(bundle_path or default_map_path(), destination, source)
    return RelationalProtectionReview(
        source,
        sheets,
        destination,
        private_bundle,
        sources,
        policies,
        candidate,
        validation,
        editable_fields,
        digest,
    )


def approve_relational_protection(
    review: RelationalProtectionReview, passphrase: str, *, approved: bool
) -> None:
    publish_relational_candidate(
        review.source,
        review.sheets,
        review.source_tables,
        review.policies,
        review.candidate,
        review.validation,
        review.output,
        review.bundle_path,
        passphrase,
        approved=approved,
        editable_fields=review.editable_fields,
        source_file_digest=review.source_file_digest,
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
    returned = read_excel(returned_path, returned_sheet, allow_reordered_headings=True)
    returned_names = list_excel_sheets(returned_path)
    selected_names = (
        (returned_sheet,)
        if isinstance(returned_sheet, str)
        else returned_sheet
        if isinstance(returned_sheet, tuple)
        else returned_names
    )
    new_sheet_names = tuple(name for name in returned_names if name not in selected_names)
    analysis_sheets = (
        read_excel_sheets(
            returned_path,
            new_sheet_names,
            allow_cached_formulas=True,
            allow_cached_formula_blanks=True,
        )
        if new_sheet_names
        else {}
    )
    restored_sheet_name = selected_names[0] if len(selected_names) == 1 else "SafeSet"
    review_analysis_sheets(analysis_sheets, (restored_sheet_name,), len(source.rows))
    new_columns = review_reconstruction(source, returned, bundle)
    return ReconstructionReview(
        source_path,
        returned_path,
        bundle_path,
        destination,
        source,
        returned,
        analysis_sheets,
        bundle,
        new_columns,
        restored_sheet_name,
        selected_names,
        source_sheet,
        returned_sheet,
    )


def approve_reconstruction(
    review: ReconstructionReview,
    approved_results: tuple[str, ...],
    approved_sheets: tuple[str, ...] = (),
    *,
    authorised: bool,
) -> int:
    if not authorised:
        raise SafetyError("Explicit restoration authorisation is required.")
    # Re-read both untrusted workbooks before publication so review cannot go stale.
    current_source = read_excel(
        review.source_path, review.source_sheet, allow_cached_formulas=True, allow_source_dates=True
    )
    current_returned = read_excel(
        review.returned_path, review.returned_sheet, allow_reordered_headings=True
    )
    current_names = list_excel_sheets(review.returned_path)
    reviewed_names = (*review.returned_bound_sheets, *review.analysis_sheets)
    if set(current_names) != set(reviewed_names):
        raise SafetyError("A workbook changed after restoration review.")
    current_analysis = (
        read_excel_sheets(
            review.returned_path,
            tuple(review.analysis_sheets),
            allow_cached_formulas=True,
            allow_cached_formula_blanks=True,
        )
        if review.analysis_sheets
        else {}
    )
    if (
        current_source != review.source_table
        or current_returned != review.returned_table
        or current_analysis != review.analysis_sheets
    ):
        raise SafetyError("A workbook changed after restoration review.")
    restored = reconstruct(current_source, current_returned, review.bundle, approved_results)
    approved_analysis = approved_analysis_sheets(
        current_analysis,
        (review.restored_sheet_name,),
        approved_sheets,
        len(current_source.rows),
    )
    destination = output_destination(
        review.output, review.returned_path, review.source_path, review.bundle_path
    )
    workbook = (
        excel_workbook_bytes({review.restored_sheet_name: restored, **approved_analysis})
        if approved_analysis
        else excel_bytes(restored)
    )
    publish(destination, workbook)
    return len(restored.rows)


def prepare_relational_reconstruction(
    returned_path: Path,
    source_path: Path,
    bundle_path: Path,
    output: Path,
    passphrase: str,
) -> RelationalReconstructionReview:
    require_excel_path(output)
    destination = output_destination(output, returned_path, source_path, bundle_path)
    bundle = read_relational_bundle(bundle_path, passphrase, returned_path, source_path, output)
    if bundle["version"] == 4 and file_digest(source_path) != bundle["source_file_digest"]:
        raise SafetyError("Original workbook does not match the relational restoration bundle.")
    sheets = tuple(bundle["sheets"])
    returned_names = list_excel_sheets(returned_path, reject_hidden=True)
    if not set(sheets).issubset(returned_names):
        raise SafetyError(
            "Returned relational workbook worksheet coverage does not match the bundle."
        )
    sources = read_excel_sheets(
        source_path, sheets, allow_cached_formulas=True, allow_source_dates=True
    )
    returned = read_excel_sheets(returned_path, sheets, allow_reordered_headings=True)
    new_sheet_names = tuple(name for name in returned_names if name not in sheets)
    if bundle["version"] == 4 and new_sheet_names:
        raise SafetyError("Editing workbooks must preserve the original protected fields only.")
    analysis_sheets = (
        read_excel_sheets(
            returned_path,
            new_sheet_names,
            allow_cached_formulas=True,
            allow_cached_formula_blanks=True,
        )
        if new_sheet_names
        else {}
    )
    review_analysis_sheets(
        analysis_sheets, sheets, sum(len(table.rows) for table in sources.values())
    )
    new_columns = review_relational_reconstruction(sources, returned, bundle)
    changes = relational_changes(sources, returned, bundle) if bundle["version"] == 4 else None
    workbook_bytes = None
    if changes is not None:
        proposal = reconstruct_relational(
            sources,
            returned,
            bundle,
            new_columns,
            approved_changes={sheet: tuple(columns) for sheet, columns in changes.items()},
        )
        workbook_bytes = patched_workbook_bytes(source_path, bundle, proposal)
    return RelationalReconstructionReview(
        source_path,
        returned_path,
        bundle_path,
        destination,
        sources,
        returned,
        analysis_sheets,
        bundle,
        new_columns,
        returned_names,
        changes,
        workbook_bytes,
    )


def approve_relational_reconstruction(
    review: RelationalReconstructionReview,
    approved_results: dict[str, tuple[str, ...]],
    approved_sheets: tuple[str, ...] = (),
    *,
    authorised: bool,
    approved_changes: dict[str, tuple[str, ...]] | None = None,
) -> int:
    if not authorised:
        raise SafetyError("Explicit relational restoration authorisation is required.")
    if review.bundle["version"] == 4 and (
        file_digest(review.source_path) != review.bundle["source_file_digest"]
    ):
        raise SafetyError("A workbook changed after relational restoration review.")
    sheets = tuple(review.bundle["sheets"])
    returned_names = list_excel_sheets(review.returned_path, reject_hidden=True)
    if returned_names != review.visible_returned_sheets:
        raise SafetyError("A workbook changed after relational restoration review.")
    current_sources = read_excel_sheets(
        review.source_path, sheets, allow_cached_formulas=True, allow_source_dates=True
    )
    current_returned = read_excel_sheets(
        review.returned_path, sheets, allow_reordered_headings=True
    )
    current_analysis = (
        read_excel_sheets(
            review.returned_path,
            tuple(review.analysis_sheets),
            allow_cached_formulas=True,
            allow_cached_formula_blanks=True,
        )
        if review.analysis_sheets
        else {}
    )
    if (
        current_sources != review.source_tables
        or current_returned != review.returned_tables
        or current_analysis != review.analysis_sheets
    ):
        raise SafetyError("A workbook changed after relational restoration review.")
    restored = reconstruct_relational(
        current_sources,
        current_returned,
        review.bundle,
        approved_results,
        current_analysis,
        approved_sheets,
        approved_changes,
    )
    destination = output_destination(
        review.output, review.returned_path, review.source_path, review.bundle_path
    )
    encoded = (
        patched_workbook_bytes(review.source_path, review.bundle, restored)
        if review.bundle["version"] == 4
        else excel_workbook_bytes(restored)
    )
    if review.bundle["version"] == 4 and encoded != review.workbook_bytes:
        raise SafetyError("A workbook changed after relational restoration review.")
    publish(destination, encoded)
    return sum(len(table.rows) for table in current_sources.values())


def inspect_source(source: Path, sheet: str | tuple[str, ...] | None = None) -> dict:
    """Return aggregate characteristics only; the UI does not show cell samples."""
    return inspect_table(
        read_excel(source, sheet, allow_cached_formulas=True, allow_source_dates=True)
    )


def locate_unsafe_source_cells(
    source: Path,
    bundle_path: Path,
    passphrase: str,
    *,
    relational: bool,
    sheet: str | tuple[str, ...] | None = None,
) -> dict:
    """Return bounded cell coordinates only after authenticating the source binding."""
    locations: list[dict[str, str]] = []
    count = 0

    def observe(worksheet: str, coordinate: str, value: str) -> None:
        nonlocal count
        if has_control(value):
            count += 1
            if len(locations) < 20:
                locations.append({"sheet": worksheet, "cell": coordinate})

    if relational:
        bundle = read_relational_bundle(bundle_path, passphrase, source)
        sources = read_excel_sheets(
            source,
            tuple(bundle["sheets"]),
            allow_cached_formulas=True,
            allow_source_dates=True,
            observe_cell=observe,
        )
        if workbook_digest(sources) != bundle["workbook_digest"]:
            raise SafetyError("Original workbook does not match the relational restoration bundle.")
    else:
        bundle = read_bundle(bundle_path, passphrase, source)
        table = read_excel(
            source,
            sheet,
            allow_cached_formulas=True,
            allow_source_dates=True,
            observe_cell=observe,
        )
        if (
            table.columns != tuple(bundle["source_columns"])
            or source_digest(table) != bundle["source_digest"]
        ):
            raise SafetyError("Original source does not match the restoration bundle.")
    return {"count": count, "cells": locations}


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
