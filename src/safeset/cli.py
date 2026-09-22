"""Value-free reporting and explicit human authorisation at the CLI boundary."""

import getpass
import json
import warnings
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Annotated

import typer

from .classification import inspect_table
from .diagnostics import log_path, record, record_reason
from .errors import SafetyError
from .ingestion import excel_bytes, read_excel, require_excel_path
from .mapping import read_mapping
from .policy import load_policy
from .restoration import restore
from .storage import default_map_path, output_destination, publish
from .transform import sanitise
from .validation import validate
from .workflow import export_candidate

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


def secret(*, confirm: bool = False) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass("Mapping passphrase: ")
            if confirm and value != getpass.getpass("Confirm mapping passphrase: "):
                raise SafetyError("Passphrases do not match.")
    except (getpass.GetPassWarning, EOFError):
        raise SafetyError("A terminal with hidden passphrase entry is required.") from None
    if len(value) < 16:
        raise SafetyError("Mapping passphrase must contain at least 16 characters.")
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
    table = read_excel(input_path, tuple(sheet) if sheet else None)
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
    table = read_excel(input_path, tuple(sheet) if sheet else None)
    record("cli.sanitise", "source_read")
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


@app.command("restore")
@guarded
def restore_command(
    input_path: Path,
    map_path: Annotated[Path, typer.Option("--map")],
    output: Annotated[Path, typer.Option()],
    authorise: Annotated[bool, typer.Option("--authorise")] = False,
    result_column: Annotated[list[str] | None, typer.Option("--result-column")] = None,
    sheet: Annotated[list[str] | None, typer.Option("--sheet")] = None,
) -> None:
    """Restore exact source keys locally into a sensitive Excel workbook."""
    if not authorise:
        raise SafetyError("Use --authorise to explicitly authorise local re-identification.")
    record("cli.restore", "approval_received")
    require_excel_path(output)
    destination = output_destination(output, input_path, map_path)
    analysed = read_excel(input_path, tuple(sheet) if sheet else None)
    record("cli.restore", "source_read")
    mapping = read_mapping(map_path, secret(), input_path, output)
    record("cli.restore", "map_unlocked")
    restored = restore(analysed, mapping, tuple(result_column or ()))
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
