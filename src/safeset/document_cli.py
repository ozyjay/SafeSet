"""CLI entry points for SafeSet DOCX protection/restoration."""

from __future__ import annotations

import getpass
from pathlib import Path

import typer

from .document import DocumentTerm, inspect_document
from .document_flow import (
    approve_document_protection,
    approve_document_restoration,
    prepare_document_protection,
    prepare_document_restoration,
)
from .errors import SafetyError

app = typer.Typer(help="Protect and restore DOCX research documents locally.")


def _secret(confirm: bool = False) -> str:
    first = getpass.getpass("Private bundle passphrase: ")
    if confirm:
        second = getpass.getpass("Confirm passphrase: ")
        if first != second:
            raise typer.BadParameter("Passphrases do not match.")
    return first


def _terms(people: list[str], identifiers: list[str]) -> tuple[DocumentTerm, ...]:
    return tuple(
        [DocumentTerm(value, "person") for value in people]
        + [DocumentTerm(value, "identifier") for value in identifiers]
    )


@app.command()
def inspect(source: Path) -> None:
    """Show only aggregate local DOCX findings."""
    try:
        review = inspect_document(source)
    except SafetyError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from None
    typer.echo(f"Email identifiers: {review.email_count}")
    typer.echo(f"ORCID identifiers: {review.orcid_count}")
    typer.echo(f"Comments: {review.comments}")
    typer.echo(f"Tracked changes: {review.tracked_changes}")
    typer.echo(f"Hidden text markers: {review.hidden_text}")
    typer.echo(f"Embedded/active objects: {review.embedded_objects}")
    typer.echo(f"Authoring metadata fields: {review.metadata_fields}")
    typer.echo(f"Custom-properties part: {review.custom_properties}")
    typer.echo(f"External relationships: {review.external_relationships}")
    if review.blockers:
        typer.echo("Protection blockers: " + ", ".join(review.blockers))


@app.command()
def protect(
    source: Path,
    output: Path = typer.Option(..., "--output"),
    bundle: Path | None = typer.Option(None, "--bundle"),
    person: list[str] | None = typer.Option(None, "--person"),
    identifier: list[str] | None = typer.Option(None, "--identifier"),
    keep_comments: bool = typer.Option(
        False,
        "--keep-comments",
        help="Keep comments only when none exist; comments otherwise block protection.",
    ),
    authorise: bool = typer.Option(False, "--authorise"),
) -> None:
    """Review and, with --authorise, create a protected DOCX and private bundle."""
    try:
        review = prepare_document_protection(
            source,
            _terms(person or [], identifier or []),
            output,
            bundle,
            remove_comments=not keep_comments,
        )
        typer.echo(f"Identifiers protected: {review.replacement_count}")
        typer.echo(f"Protected occurrences: {review.replacement_occurrences}")
        typer.echo(f"Comments removed: {'yes' if review.comments_removed else 'no'}")
        typer.echo(f"Protected copy: {review.output}")
        typer.echo(f"Private bundle: {review.bundle_path}")
        typer.echo(
            "This review does not establish anonymity or suitability for the intended recipient."
        )
        if not authorise:
            typer.echo("Nothing created. Re-run with --authorise after reviewing this summary.")
            return
        approve_document_protection(review, _secret(confirm=True), approved=True)
        typer.echo("Protected document and private restoration bundle created.")
    except SafetyError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from None


@app.command()
def restore(
    returned: Path,
    bundle: Path = typer.Option(..., "--bundle"),
    output: Path = typer.Option(..., "--output"),
    authorise: bool = typer.Option(False, "--authorise"),
) -> None:
    """Review and, with --authorise, restore protected identifiers locally."""
    try:
        secret = _secret()
        review = prepare_document_restoration(returned, bundle, output, secret)
        typer.echo(f"Identifiers to restore: {review.replacement_count}")
        typer.echo(f"Protected occurrences to restore: {review.replacement_occurrences}")
        typer.echo(f"Restored output: {review.output}")
        if not authorise:
            typer.echo("Nothing created. Re-run with --authorise after reviewing this summary.")
            return
        approve_document_restoration(review, authorised=True)
        typer.echo("A new locally reidentified DOCX was created. Keep it private.")
    except SafetyError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from None


if __name__ == "__main__":
    app()
