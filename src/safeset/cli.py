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
from .errors import SafetyError
from .ingestion import csv_bytes, read_csv
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
    @wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except SafetyError as error:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from None
        except (OSError, UnicodeError):
            typer.echo("Error: Local file operation failed; no sensitive details shown.", err=True)
            raise typer.Exit(1) from None

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


@app.command("inspect")
@guarded
def inspect_command(input_path: Path) -> None:
    """Inspect headings and aggregate local characteristics, without cell samples."""
    report(inspect_table(read_csv(input_path)))


@app.command("sanitise")
@guarded
def sanitise_command(
    input_path: Path,
    policy: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    create_map: Annotated[bool, typer.Option("--create-map")] = False,
    map_path: Annotated[Path | None, typer.Option("--map")] = None,
    approve_export: Annotated[bool, typer.Option("--approve-export")] = False,
) -> None:
    """Review, validate and explicitly approve a minimised export with a separate map."""
    if not create_map:
        raise SafetyError("Use --create-map to explicitly authorise encrypted mapping creation.")
    parsed = load_policy(policy)
    candidate = sanitise(read_csv(input_path), parsed)
    validation = validate(candidate.table, parsed)
    report(validation.summary())
    validation.require_pass()
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
    typer.echo("Export and encrypted mapping created. Keep the mapping local and separate.")


@app.command("validate")
@guarded
def validate_command(input_path: Path, policy: Annotated[Path, typer.Option()]) -> None:
    """Check a candidate dataset; failure returns a non-zero status."""
    validation = validate(read_csv(input_path), load_policy(policy))
    report(validation.summary())
    validation.require_pass()


@app.command("restore")
@guarded
def restore_command(
    input_path: Path,
    map_path: Annotated[Path, typer.Option("--map")],
    output: Annotated[Path, typer.Option()],
    authorise: Annotated[bool, typer.Option("--authorise")] = False,
    result_column: Annotated[list[str] | None, typer.Option("--result-column")] = None,
) -> None:
    """Restore exact source keys locally. The resulting CSV contains sensitive plaintext."""
    if not authorise:
        raise SafetyError("Use --authorise to explicitly authorise local re-identification.")
    destination = output_destination(output, input_path, map_path)
    analysed = read_csv(input_path)
    mapping = read_mapping(map_path, secret(), input_path, output)
    restored = restore(analysed, mapping, tuple(result_column or ()))
    report(
        {
            "rows": len(restored.rows),
            "result_columns": len(result_column or ()),
            "notice": "Authorised restoration produces sensitive local plaintext.",
        }
    )
    publish(destination, csv_bytes(restored))
    typer.echo("Restoration complete. Do not upload restored data.")
