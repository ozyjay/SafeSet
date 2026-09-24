"""Review/approval boundaries for protected DOCX workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .document import (
    DocumentInspection,
    DocumentTerm,
    document_digest,
    protect_document_bytes,
    read_docx,
    require_docx_path,
    restore_document_bytes,
)
from .document_bundle import encrypt_document_bundle, read_document_bundle
from .errors import SafetyError
from .pseudonyms import new_id
from .storage import (
    default_map_path,
    map_destination,
    output_destination,
    private_directory,
    publish,
)


@dataclass(repr=False)
class DocumentProtectionReview:
    source_path: Path
    output: Path
    bundle_path: Path
    source_digest: str
    protected_digest: str
    protected_bytes: bytes = field(repr=False)
    bundle: dict = field(repr=False)
    inspection: DocumentInspection
    replacement_count: int
    replacement_occurrences: int
    comments_removed: bool


@dataclass(repr=False)
class DocumentRestorationReview:
    returned_path: Path
    output: Path
    bundle_path: Path
    returned_digest: str
    restored_bytes: bytes = field(repr=False)
    replacement_count: int
    replacement_occurrences: int


def _bundle_destination(path: Path | None, output: Path, source: Path) -> Path:
    selected = default_map_path() if path is None else Path(path)
    if selected.suffix.lower() != ".enc":
        raise SafetyError("Private document bundle must have an .enc filename.")
    return map_destination(selected, output, source)


def prepare_document_protection(
    source_path: Path,
    terms: tuple[DocumentTerm, ...],
    output: Path,
    bundle_path: Path | None = None,
    *,
    remove_comments: bool = True,
) -> DocumentProtectionReview:
    source_path = Path(source_path)
    source = read_docx(source_path)
    require_docx_path(output)
    output = output_destination(Path(output), source_path)
    bundle_path = _bundle_destination(bundle_path, output, source_path)
    protected, replacements, inspection = protect_document_bytes(
        source, terms, remove_comments=remove_comments
    )
    bundle = {
        "version": 1,
        "document_id": new_id(),
        "source_digest": document_digest(source),
        "protected_digest": document_digest(protected),
        "replacements": [dict(item) for item in replacements],
        "comments_removed": bool(remove_comments and inspection.comments),
    }
    return DocumentProtectionReview(
        source_path=source_path.resolve(),
        output=output,
        bundle_path=bundle_path,
        source_digest=bundle["source_digest"],
        protected_digest=bundle["protected_digest"],
        protected_bytes=protected,
        bundle=bundle,
        inspection=inspection,
        replacement_count=len(replacements),
        replacement_occurrences=sum(item["count"] for item in replacements),
        comments_removed=bundle["comments_removed"],
    )


def approve_document_protection(
    review: DocumentProtectionReview,
    passphrase: str,
    *,
    approved: bool,
) -> None:
    if not approved:
        raise SafetyError("Explicit document protection approval is required.")
    current = read_docx(review.source_path)
    if document_digest(current) != review.source_digest:
        raise SafetyError("Word document changed after protection review.")
    output = output_destination(review.output, review.source_path)
    bundle_path = map_destination(review.bundle_path, output, review.source_path)
    encrypted = encrypt_document_bundle(review.bundle, passphrase)
    private_directory(bundle_path.parent, create=True)
    publish(bundle_path, encrypted)
    try:
        publish(output, review.protected_bytes)
    except SafetyError:
        raise SafetyError(
            "Document protection publication failed; a private bundle was retained."
        ) from None


def prepare_document_restoration(
    returned_path: Path,
    bundle_path: Path,
    output: Path,
    passphrase: str,
) -> DocumentRestorationReview:
    returned_path = Path(returned_path)
    returned = read_docx(returned_path)
    bundle = read_document_bundle(Path(bundle_path), passphrase, returned_path, Path(output))
    require_docx_path(output)
    output = output_destination(Path(output), returned_path, Path(bundle_path))
    restored = restore_document_bytes(returned, tuple(bundle["replacements"]))
    return DocumentRestorationReview(
        returned_path=returned_path.resolve(),
        output=output,
        bundle_path=Path(bundle_path).resolve(),
        returned_digest=document_digest(returned),
        restored_bytes=restored,
        replacement_count=len(bundle["replacements"]),
        replacement_occurrences=sum(item["count"] for item in bundle["replacements"]),
    )


def approve_document_restoration(
    review: DocumentRestorationReview,
    *,
    authorised: bool,
) -> None:
    if not authorised:
        raise SafetyError("Explicit document restoration authorisation is required.")
    current = read_docx(review.returned_path)
    if document_digest(current) != review.returned_digest:
        raise SafetyError("Word document changed after restoration review.")
    output = output_destination(review.output, review.returned_path, review.bundle_path)
    publish(output, review.restored_bytes)
