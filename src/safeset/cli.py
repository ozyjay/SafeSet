"""Value-free reporting and explicit human authorisation at the CLI boundary."""

import getpass
import json
import warnings
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Annotated

import typer

from .bundle import read_bundle
from .classification import inspect_table
from .diagnostics import log_path, record, record_reason
from .errors import SafetyError
from .ingestion import excel_bytes, read_excel, require_excel_path
from .mapping import read_mapping
from .policy import load_policy
from .reconstruction import reconstruct, review_reconstruction
from .relational import (
    publish_relational_candidate,
    read_relational_bundle,
    reconstruct_relational,
    review_relational_reconstruction,
    sanitise_relational,
    validate_relational,
)
from .restoration import restore
from .storage import default_map_path, output_destination, publish
from .transform import sanitise
from .validation import validate
from .workflow import export_candidate, protect_candidate

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Local minimisation and pseudonymisation. No anonymity guarantee.",
)


def guarded(function: Callable) -> Callable:
    stage = {
        "inspect_command": "cli.inspect",
        "sanitise_command": "cli.sanitise",
        "validate_command": "cli.validate",
        "restore_command": "cli.restore",
        "protect_command": "cli.sanitise",
        "reconstruct_command": "cli.restore",
        "protect_relational_command": "cli.sanitise",
        "reconstruct_relational_command": "cli.restore",
    }[function.__name__]

    @wraps(function)
    def wrapper(*args, **kwargs):
        record(stage, "start")
        try:
            result = function(*args, **kwargs)
        except SafetyError as error:
            record(stage, "rejected")
            record_reason(stage, error)
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from None
        except (OSError, UnicodeError):
            record(stage, "io_error")
            typer.echo("Error: Local file operation failed; no sensitive details shown.", err=True)
            raise typer.Exit(1) from None
        record(stage, "success")
        return result

    return wrapper


def report(summary: dict) -> None:
    typer.echo(json.dumps(summary, indent=2, ensure_ascii=True))


def secret(*, confirm: bool = False, bundle: bool = False) -> str:
    label = "Restoration" if bundle else "Mapping"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass(f"{label} passphrase: ")
            if confirm and value != getpass.getpass(f"Confirm {label.lower()} passphrase: "):
                raise SafetyError("Passphrases do not match.")
    except (getpass.GetPassWarning, EOFError):
        raise SafetyError("A terminal with hidden passphrase entry is required.") from None
    if len(value) < 16:
        raise SafetyError(f"{label} passphrase must contain at least 16 characters.")
    return value


@app.command("desktop")
def desktop_command() -> None:
    """Open the offline desktop interface."""
    from .desktop import main

    main()


@app.command("log-path")
def log_path_command() -> None:
    """Show the local diagnostic log location without reading its contents."""
    if not record("cli.log_path", "start"):
        typer.echo("Notice: diagnostic log is unavailable.", err=True)
    typer.echo(str(log_path()))


@app.command("inspect")
@guarded
def inspect_command(
    input_path: Path, sheet: Annotated[list[str] | None, typer.Option("--sheet")] = None
) -> None:
    """Inspect headings and aggregate local characteristics, without cell samples."""
    table = read_excel(
        input_path,
        tuple(sheet) if sheet else None,
        allow_cached_formulas=True,
        allow_source_dates=True,
    )
    record("cli.inspect", "source_read")
    report(inspect_table(table))


@app.command("sanitise")
@guarded
def sanitise_command(
    input_path: Path,
    policy: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    create_map: Annotated[bool, typer.Option("--create-map")] = False,
    map_path: Annotated[Path | None, typer.Option("--map")] = None,
    approve_export: Annotated[bool, typer.Option("--approve-export")] = False,
    sheet: Annotated[list[str] | None, typer.Option("--sheet")] = None,
) -> None:
    """Review, validate and explicitly approve a minimised export with a separate map."""
    if not create_map:
        raise SafetyError("Use --create-map to explicitly authorise encrypted mapping creation.")
    parsed = load_policy(policy)
    record("cli.sanitise", "policy_loaded")
    table = read_excel(
        input_path,
        tuple(sheet) if sheet else None,
        allow_cached_formulas=True,
        allow_source_dates=True,
    )
    record("cli.sanitise", "source_read")
    if table.formula_cells:
        typer.echo(
            f"Notice: {table.formula_cells} saved formula results were used. "
            "Recalculate and save the source workbook locally before export."
        )
    if table.date_cells:
        typer.echo(
            f"Notice: {table.date_cells} Excel date/time cells were read as text. "
            "Review their necessity and minimise them in the policy."
        )
    candidate = sanitise(table, parsed)
    record("cli.sanitise", "candidate_ready")
    validation = validate(candidate.table, parsed)
    report(validation.summary())
    validation.require_pass()
    record("cli.sanitise", "validation_passed")
    destination = map_path or default_map_path()
    # A map location is operational metadata, shown only after review; JSON escapes controls.
    report(
        {
            "mapping_destination": str(destination.expanduser()),
            "export_destination": str(output.expanduser()),
            "dropped_columns": sum(r.action == "drop" for r in parsed.columns.values()),
        }
    )
    if not approve_export and not typer.confirm(
        "Approve this export for its intended recipient?", default=False
    ):
        raise SafetyError("Export declined; no artefacts created.")
    record("cli.sanitise", "approval_received")
    export_candidate(
        candidate,
        parsed,
        output,
        destination,
        secret(confirm=True),
        approved=True,
        create_map=True,
        source_path=input_path,
    )
    record("cli.sanitise", "published")
    typer.echo("Export and encrypted mapping created. Keep the mapping local and separate.")


@app.command("validate")
@guarded
def validate_command(
    input_path: Path,
    policy: Annotated[Path, typer.Option()],
    sheet: Annotated[list[str] | None, typer.Option("--sheet")] = None,
) -> None:
    """Check a candidate dataset; failure returns a non-zero status."""
    table = read_excel(input_path, tuple(sheet) if sheet else None)
    record("cli.validate", "source_read")
    parsed = load_policy(policy)
    record("cli.validate", "policy_loaded")
    validation = validate(table, parsed)
    report(validation.summary())
    validation.require_pass()
    record("cli.validate", "validation_passed")


@app.command("protect")
@guarded
def protect_command(
    input_path: Path,
    policy: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    create_bundle: Annotated[bool, typer.Option("--create-bundle")] = False,
    bundle_path: Annotated[Path | None, typer.Option("--bundle")] = None,
    approve_export: Annotated[bool, typer.Option("--approve-export")] = False,
    sheet: Annotated[list[str] | None, typer.Option("--sheet")] = None,
    validation_profile: Annotated[str, typer.Option("--validation-profile")] = "strict",
) -> None:
    """Create a protected working copy and encrypted version 2 restoration bundle."""
    if not create_bundle:
        raise SafetyError("Use --create-bundle to authorise private bundle creation.")
    parsed = load_policy(policy)
    table = read_excel(
        input_path,
        tuple(sheet) if sheet else None,
        allow_cached_formulas=True,
        allow_source_dates=True,
    )
    candidate = sanitise(table, parsed)
    validation = validate(candidate.table, parsed, validation_profile)
    report(validation.summary())
    validation.require_pass()
    require_excel_path(output)
    destination = output_destination(output, input_path, policy)
    from .storage import map_destination

    private_bundle = map_destination(
        bundle_path or default_map_path(), destination, input_path, policy
    )
    report({"protected_destination": str(destination), "private_bundle": str(private_bundle)})
    if not approve_export and not typer.confirm(
        "Approve this protected workbook for its intended use?", default=False
    ):
        raise SafetyError("Protection declined; no artefacts created.")
    protect_candidate(
        table,
        candidate,
        parsed,
        destination,
        private_bundle,
        secret(confirm=True, bundle=True),
        approved=True,
        source_path=input_path,
        sheet=tuple(sheet) if sheet else None,
        validation_profile=validation_profile,
    )
    typer.echo("Protected workbook and private restoration bundle created.")


@app.command("reconstruct")
@guarded
def reconstruct_command(
    input_path: Path,
    original_source: Annotated[Path, typer.Option("--original-source")],
    bundle_path: Annotated[Path, typer.Option("--bundle")],
    output: Annotated[Path, typer.Option()],
    authorise: Annotated[bool, typer.Option("--authorise")] = False,
    result_column: Annotated[list[str] | None, typer.Option("--result-column")] = None,
    sheet: Annotated[list[str] | None, typer.Option("--sheet")] = None,
    source_sheet: Annotated[list[str] | None, typer.Option("--source-sheet")] = None,
) -> None:
    """Reconstruct a new local workbook from the bound source and approved results."""
    require_excel_path(output)
    destination = output_destination(output, input_path, original_source, bundle_path)
    bundle = read_bundle(bundle_path, secret(bundle=True), input_path, original_source, output)
    source = read_excel(
        original_source,
        tuple(source_sheet) if source_sheet else None,
        allow_cached_formulas=True,
        allow_source_dates=True,
    )
    returned = read_excel(input_path, tuple(sheet) if sheet else None)
    new_columns = review_reconstruction(source, returned, bundle)
    approved = tuple(result_column or ())
    if len(set(approved)) != len(approved) or set(approved) != set(new_columns):
        raise SafetyError("Every new result field needs explicit --result-column approval.")
    report(
        {
            "records": len(returned.rows),
            "new_result_columns": len(new_columns),
            "restored_source_columns": len(source.columns),
            "output": str(destination),
            "notice": "Reconstruction produces sensitive local plaintext.",
        }
    )
    if not authorise and not typer.confirm(
        "Authorise local re-identification and new workbook creation?", default=False
    ):
        raise SafetyError("Restoration declined; no artefact created.")
    restored = reconstruct(source, returned, bundle, approved)
    publish(destination, excel_bytes(restored))
    typer.echo("Reconstruction complete. Keep the restored workbook private.")


def _sheet_policies(values: list[str]) -> tuple[tuple[str, ...], dict[str, object]]:
    result = {}
    for value in values:
        if "=" not in value:
            raise SafetyError("Use --sheet-policy Worksheet=policy.yaml for every worksheet.")
        sheet, raw_path = value.split("=", 1)
        if not sheet or not raw_path or sheet in result:
            raise SafetyError("Relational worksheet policies are missing or duplicated.")
        result[sheet] = load_policy(Path(raw_path))
    if not result:
        raise SafetyError("At least one --sheet-policy is required.")
    return tuple(result), result


@app.command("protect-relational")
@guarded
def protect_relational_command(
    input_path: Path,
    sheet_policy: Annotated[list[str], typer.Option("--sheet-policy")],
    output: Annotated[Path, typer.Option()],
    create_bundle: Annotated[bool, typer.Option("--create-bundle")] = False,
    bundle_path: Annotated[Path | None, typer.Option("--bundle")] = None,
    approve_export: Annotated[bool, typer.Option("--approve-export")] = False,
    validation_profile: Annotated[str, typer.Option("--validation-profile")] = "strict",
    shared_code_field: Annotated[list[str] | None, typer.Option("--shared-code-field")] = None,
) -> None:
    """Protect related worksheets with shared random entity IDs and separate row IDs."""
    if not create_bundle:
        raise SafetyError("Use --create-bundle to authorise private bundle creation.")
    sheets, policies = _sheet_policies(sheet_policy)
    from .ingestion import read_excel_sheets

    sources = read_excel_sheets(
        input_path, sheets, allow_cached_formulas=True, allow_source_dates=True
    )
    candidate = sanitise_relational(sources, policies, tuple(shared_code_field or ()))
    validation = validate_relational(candidate, policies, validation_profile)
    report(validation.summary())
    validation.require_pass()
    require_excel_path(output)
    destination = output_destination(
        output, input_path, *(Path(v.split("=", 1)[1]) for v in sheet_policy)
    )
    from .storage import map_destination

    private_bundle = map_destination(bundle_path or default_map_path(), destination, input_path)
    report(
        {
            "worksheets": len(sheets),
            "validation_profile": validation_profile,
            "shared_code_fields": list(candidate.shared_code_fields),
            "protected_destination": str(destination),
            "private_bundle": str(private_bundle),
            "notice": "Shared entity IDs deliberately expose cross-sheet linkability.",
        }
    )
    if not approve_export and not typer.confirm(
        "Approve this linked protected workbook for its intended use?", default=False
    ):
        raise SafetyError("Protection declined; no artefacts created.")
    publish_relational_candidate(
        input_path,
        sheets,
        sources,
        policies,
        candidate,
        validation,
        destination,
        private_bundle,
        secret(confirm=True, bundle=True),
        approved=True,
    )
    typer.echo("Linked protected workbook and private restoration bundle created.")


def _relational_result_columns(
    values: list[str], sheets: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {sheet: [] for sheet in sheets}
    for value in values:
        if "=" not in value:
            raise SafetyError("Use --result-column Worksheet=Column for relational results.")
        sheet, column = value.split("=", 1)
        if sheet not in result or not column or column in result[sheet]:
            raise SafetyError("Relational result approval is invalid or duplicated.")
        result[sheet].append(column)
    return {sheet: tuple(columns) for sheet, columns in result.items()}


@app.command("reconstruct-relational")
@guarded
def reconstruct_relational_command(
    input_path: Path,
    original_source: Annotated[Path, typer.Option("--original-source")],
    bundle_path: Annotated[Path, typer.Option("--bundle")],
    output: Annotated[Path, typer.Option()],
    authorise: Annotated[bool, typer.Option("--authorise")] = False,
    result_column: Annotated[list[str] | None, typer.Option("--result-column")] = None,
) -> None:
    """Reconstruct all worksheets from a version 3 relational bundle."""
    require_excel_path(output)
    destination = output_destination(output, input_path, original_source, bundle_path)
    bundle = read_relational_bundle(
        bundle_path, secret(bundle=True), input_path, original_source, output
    )
    sheets = tuple(bundle["sheets"])
    from .ingestion import excel_workbook_bytes, list_excel_sheets, read_excel_sheets

    if set(list_excel_sheets(input_path)) != set(sheets):
        raise SafetyError(
            "Returned relational workbook worksheet coverage does not match the bundle."
        )
    sources = read_excel_sheets(
        original_source, sheets, allow_cached_formulas=True, allow_source_dates=True
    )
    returned = read_excel_sheets(input_path, sheets)
    available = review_relational_reconstruction(sources, returned, bundle)
    approved = _relational_result_columns(result_column or [], sheets)
    if any(set(approved[sheet]) != set(available[sheet]) for sheet in sheets):
        raise SafetyError("Every new relational result field needs explicit approval.")
    report(
        {
            "worksheets": len(sheets),
            "records": sum(len(table.rows) for table in returned.values()),
            "new_result_columns": sum(len(columns) for columns in available.values()),
            "output": str(destination),
            "notice": "Reconstruction produces sensitive local plaintext.",
        }
    )
    if not authorise and not typer.confirm(
        "Authorise local re-identification and new workbook creation?", default=False
    ):
        raise SafetyError("Restoration declined; no artefact created.")
    restored = reconstruct_relational(sources, returned, bundle, approved)
    publish(destination, excel_workbook_bytes(restored))
    typer.echo("Relational reconstruction complete. Keep the restored workbook private.")


@app.command("restore")
@guarded
def restore_command(
    input_path: Path,
    map_path: Annotated[Path, typer.Option("--map")],
    output: Annotated[Path, typer.Option()],
    authorise: Annotated[bool, typer.Option("--authorise")] = False,
    result_column: Annotated[list[str] | None, typer.Option("--result-column")] = None,
    sheet: Annotated[list[str] | None, typer.Option("--sheet")] = None,
    original_source: Annotated[Path | None, typer.Option("--original-source")] = None,
    policy_path: Annotated[Path | None, typer.Option("--policy")] = None,
    source_sheet: Annotated[list[str] | None, typer.Option("--source-sheet")] = None,
) -> None:
    """Restore source keys and optionally original coded category labels locally."""
    if not authorise:
        raise SafetyError("Use --authorise to explicitly authorise local re-identification.")
    if (original_source is None) != (policy_path is None) or (
        source_sheet and original_source is None
    ):
        raise SafetyError("Restoring coded labels requires both --original-source and --policy.")
    record("cli.restore", "approval_received")
    require_excel_path(output)
    if original_source is not None:
        require_excel_path(original_source)
    destination = output_destination(
        output, input_path, map_path, *(p for p in (original_source, policy_path) if p)
    )
    analysed = read_excel(input_path, tuple(sheet) if sheet else None)
    record("cli.restore", "source_read")
    mapping = read_mapping(
        map_path, secret(), input_path, output, *(p for p in (original_source, policy_path) if p)
    )
    record("cli.restore", "map_unlocked")
    original_table = (
        read_excel(
            original_source,
            tuple(source_sheet) if source_sheet else None,
            allow_cached_formulas=True,
            allow_source_dates=True,
        )
        if original_source is not None
        else None
    )
    parsed_policy = load_policy(policy_path) if policy_path is not None else None
    restored = restore(
        analysed,
        mapping,
        tuple(result_column or ()),
        coded_source=original_table,
        coded_policy=parsed_policy,
    )
    report(
        {
            "rows": len(restored.rows),
            "result_columns": len(result_column or ()),
            "notice": "Authorised restoration produces sensitive local plaintext.",
        }
    )
    publish(destination, excel_bytes(restored))
    record("cli.restore", "published")
    typer.echo("Restoration complete. Do not upload restored data.")
