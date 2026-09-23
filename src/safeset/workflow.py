"""Publication boundary: always revalidate immediately before writing."""

from pathlib import Path

from .bundle import create_bundle, encrypt_bundle, source_digest
from .errors import SafetyError
from .ingestion import MAX_BYTES, Table, excel_bytes, read_excel, require_excel_path
from .mapping import encrypt_mapping, validate_mapping
from .policy import Policy
from .storage import map_destination, output_destination, private_directory, publish
from .transform import Candidate
from .validation import validate


def protect_candidate(
    source: Table,
    candidate: Candidate,
    policy: Policy,
    output: Path,
    bundle_path: Path,
    passphrase: str,
    *,
    approved: bool,
    source_path: Path,
    sheet: str | tuple[str, ...] | None = None,
    validation_profile: str = "strict",
) -> None:
    """Publish an authenticated bundle before its protected workbook."""
    if not approved:
        raise SafetyError("Explicit protection approval is required.")
    validate(candidate.table, policy, validation_profile).require_pass()
    current = read_excel(source_path, sheet, allow_cached_formulas=True, allow_source_dates=True)
    if source_digest(current) != source_digest(source):
        raise SafetyError("Source workbook changed after protection review.")
    if len(source.rows) != len(candidate.table.rows) or any(
        candidate.mapping["records"].get(protected["record_id"]) != original[policy.source_key]
        for original, protected in zip(source.rows, candidate.table.rows, strict=True)
    ):
        raise SafetyError("Protected record identities do not match the source.")
    bundle = create_bundle(source, policy, candidate)
    if set(bundle["records"]) != {row["record_id"] for row in candidate.table.rows}:
        raise SafetyError("Protected candidate and restoration bundle do not match.")
    require_excel_path(output)
    output = output_destination(output, source_path)
    bundle_path = map_destination(bundle_path, output, source_path)
    data = excel_bytes(candidate.table)
    if len(data) > MAX_BYTES:
        raise SafetyError("Protected workbook exceeds the supported size limit.")
    encrypted = encrypt_bundle(bundle, passphrase)
    private_directory(bundle_path.parent, create=True)
    publish(bundle_path, encrypted)
    try:
        publish(output, data)
    except SafetyError:
        raise SafetyError("Protection publication failed; a private bundle was retained.") from None


def export_candidate(
    candidate: Candidate,
    policy: Policy,
    output: Path,
    map_path: Path,
    passphrase: str,
    *,
    approved: bool,
    create_map: bool,
    source_path: Path,
) -> None:
    if not approved or not create_map:
        raise SafetyError(
            "Explicit export approval and mapping creation authorisation are required."
        )
    validate(candidate.table, policy).require_pass()
    validate_mapping(candidate.mapping)
    if candidate.mapping["source_column"] != policy.source_key or set(
        candidate.mapping["records"]
    ) != {r["record_id"] for r in candidate.table.rows}:
        raise SafetyError("Candidate and mapping do not match.")
    require_excel_path(output)
    output = output_destination(output, source_path)
    map_path = map_destination(map_path, output, source_path)
    encrypted = encrypt_mapping(candidate.mapping, passphrase)
    data = excel_bytes(candidate.table)
    if len(data) > MAX_BYTES:
        raise SafetyError("Candidate export exceeds the supported Excel workbook size limit.")
    private_directory(map_path.parent, create=True)
    publish(map_path, encrypted)
    try:
        publish(output, data)
    except SafetyError:
        raise SafetyError(
            "Export publication failed; an encrypted map was retained. "
            "Review private storage before retrying."
        ) from None
