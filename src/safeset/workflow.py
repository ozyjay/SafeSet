"""Publication boundary: always revalidate immediately before writing."""

from pathlib import Path

from .errors import SafetyError
from .ingestion import MAX_BYTES, excel_bytes, require_excel_path
from .mapping import encrypt_mapping, validate_mapping
from .policy import Policy
from .storage import map_destination, output_destination, private_directory, publish
from .transform import Candidate
from .validation import validate


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
