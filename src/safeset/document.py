"""Bounded local protection and restoration for DOCX research documents.

The document workflow is intentionally conservative. It replaces only explicit
operator terms plus locally detected email/ORCID identifiers, strips common
authoring metadata, optionally removes comments, and fails closed on document
features that are not yet safe to transform.
"""

from __future__ import annotations

import hashlib
import io
import re
import secrets
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from .errors import SafetyError

MAX_DOCX_BYTES = 10 * 1024 * 1024
MAX_DOCX_UNPACKED = 50 * 1024 * 1024
MAX_DOCX_PARTS = 512
MAX_DOCX_PART_BYTES = 10 * 1024 * 1024
MAX_DOCUMENT_TERMS = 64
MAX_DOCUMENT_TERM = 256

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
ORCID_RE = re.compile(r"(?<!\d)(?:\d{4}-){3}\d{3}[\dX](?!\d)", re.IGNORECASE)

TEXT_PART_RE = re.compile(
    r"^word/(?:document|header\d+|footer\d+|footnotes|endnotes)\.xml$"
)
COMMENT_PART_RE = re.compile(
    r"^word/(?:comments(?:Extended|Extensible|Ids)?|people)\.xml$",
    re.IGNORECASE,
)

TRACKED_TAGS = {
    f"{{{W}}}ins",
    f"{{{W}}}del",
    f"{{{W}}}moveFrom",
    f"{{{W}}}moveTo",
}
COMMENT_MARKER_TAGS = {
    f"{{{W}}}commentRangeStart",
    f"{{{W}}}commentRangeEnd",
    f"{{{W}}}commentReference",
}


@dataclass(frozen=True)
class DocumentTerm:
    value: str
    kind: str = "other"


@dataclass(frozen=True)
class DocumentInspection:
    email_count: int
    orcid_count: int
    comments: int
    tracked_changes: int
    hidden_text: int
    embedded_objects: int
    custom_properties: int
    metadata_fields: int
    external_relationships: int
    blockers: tuple[str, ...]

    def summary(self) -> dict:
        return {
            "email_count": self.email_count,
            "orcid_count": self.orcid_count,
            "comments": self.comments,
            "tracked_changes": self.tracked_changes,
            "hidden_text": self.hidden_text,
            "embedded_objects": self.embedded_objects,
            "custom_properties": self.custom_properties,
            "metadata_fields": self.metadata_fields,
            "external_relationships": self.external_relationships,
            "blockers": list(self.blockers),
        }


def require_docx_path(path: Path) -> Path:
    path = Path(path)
    if path.suffix.lower() != ".docx":
        raise SafetyError("Only .docx Word documents are supported.")
    return path


def _safe_local_file(path: Path) -> Path:
    path = require_docx_path(path)
    try:
        if path.is_symlink() or not path.is_file():
            raise SafetyError("Input must be a regular local file.")
        size = path.stat().st_size
        if size <= 0 or size > MAX_DOCX_BYTES:
            raise SafetyError("Word document exceeds supported archive limits.")
        return path.resolve()
    except OSError:
        raise SafetyError("Unable to read the requested local file.") from None


def read_docx(path: Path) -> bytes:
    resolved = _safe_local_file(path)
    try:
        data = resolved.read_bytes()
    except OSError:
        raise SafetyError("Unable to read the requested local file.") from None
    validate_docx_bytes(data)
    return data


def _normalised_name(name: str) -> str:
    candidate = name.replace("\\", "/")
    if (
        not candidate
        or candidate.startswith("/")
        or "\x00" in candidate
        or any(part in {"", ".", ".."} for part in candidate.split("/"))
    ):
        raise SafetyError("Word document has an unsafe archive structure.")
    return candidate


def _read_parts(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_DOCX_BYTES:
        raise SafetyError("Word document exceeds supported archive limits.")
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_DOCX_PARTS:
                raise SafetyError("Word document exceeds supported archive limits.")
            parts: dict[str, bytes] = {}
            total = 0
            for info in infos:
                name = _normalised_name(info.filename)
                if info.is_dir():
                    continue
                if info.file_size < 0 or info.file_size > MAX_DOCX_PART_BYTES:
                    raise SafetyError("Word document exceeds supported archive limits.")
                total += info.file_size
                if total > MAX_DOCX_UNPACKED:
                    raise SafetyError("Word document exceeds supported archive limits.")
                if name in parts:
                    raise SafetyError("Word document has an unsafe archive structure.")
                parts[name] = archive.read(info)
    except (zipfile.BadZipFile, RuntimeError, ValueError, OSError):
        raise SafetyError("Input is not a supported Word document.") from None
    if "[Content_Types].xml" not in parts or "word/document.xml" not in parts:
        raise SafetyError("Input is not a supported Word document.")
    return parts


def validate_docx_bytes(data: bytes) -> None:
    parts = _read_parts(data)
    if any(name.lower().endswith("vbaproject.bin") for name in parts):
        raise SafetyError("Word document contains unsupported active content.")


def document_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_xml(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        raise SafetyError("Word document contains malformed XML.") from None


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _count_comments(parts: dict[str, bytes]) -> int:
    raw = parts.get("word/comments.xml")
    if raw is None:
        return 0
    root = _parse_xml(raw)
    return sum(1 for item in root.iter() if _local(item.tag) == "comment")


def _text_roots(parts: dict[str, bytes]) -> list[tuple[str, ET.Element]]:
    result = []
    for name, raw in parts.items():
        if TEXT_PART_RE.match(name):
            result.append((name, _parse_xml(raw)))
    return result


def _visible_text(roots: list[tuple[str, ET.Element]]) -> str:
    return "\n".join(
        node.text or ""
        for _, root in roots
        for node in root.iter()
        if node.tag == f"{{{W}}}t"
    )


def _relationship_text(parts: dict[str, bytes]) -> str:
    values = []
    for name, raw in parts.items():
        if not name.endswith(".rels"):
            continue
        root = _parse_xml(raw)
        for item in root.iter():
            values.extend(item.attrib.values())
    return "\n".join(values)


def _relationship_count(parts: dict[str, bytes]) -> int:
    total = 0
    for name, raw in parts.items():
        if not name.endswith(".rels"):
            continue
        root = _parse_xml(raw)
        total += sum(
            1
            for item in root
            if item.attrib.get("TargetMode", "").lower() == "external"
        )
    return total


def _metadata_field_count(parts: dict[str, bytes]) -> int:
    count = 0
    core = parts.get("docProps/core.xml")
    if core:
        root = _parse_xml(core)
        wanted = {"creator", "lastModifiedBy", "revision", "created", "modified"}
        count += sum(
            1 for child in root if _local(child.tag) in wanted and (child.text or "").strip()
        )
    app = parts.get("docProps/app.xml")
    if app:
        root = _parse_xml(app)
        count += sum(
            1
            for child in root
            if _local(child.tag) in {"Company", "Manager"} and (child.text or "").strip()
        )
    return count


def inspect_document_bytes(data: bytes) -> DocumentInspection:
    parts = _read_parts(data)
    roots = _text_roots(parts)
    text = _visible_text(roots) + "\n" + _relationship_text(parts)
    tracked = sum(
        1 for _, root in roots for item in root.iter() if item.tag in TRACKED_TAGS
    )
    hidden = sum(
        1 for _, root in roots for item in root.iter() if item.tag == f"{{{W}}}vanish"
    )
    embedded = sum(
        1
        for name in parts
        if name.startswith("word/embeddings/") or name.lower().endswith("vbaproject.bin")
    )
    blockers = []
    if tracked:
        blockers.append("tracked_changes")
    if hidden:
        blockers.append("hidden_text")
    if embedded:
        blockers.append("embedded_objects")
    return DocumentInspection(
        email_count=len(set(EMAIL_RE.findall(text))),
        orcid_count=len(set(ORCID_RE.findall(text))),
        comments=_count_comments(parts),
        tracked_changes=tracked,
        hidden_text=hidden,
        embedded_objects=embedded,
        custom_properties=1 if "docProps/custom.xml" in parts else 0,
        metadata_fields=_metadata_field_count(parts),
        external_relationships=_relationship_count(parts),
        blockers=tuple(blockers),
    )


def inspect_document(path: Path) -> DocumentInspection:
    return inspect_document_bytes(read_docx(path))


def _validate_terms(terms: tuple[DocumentTerm, ...]) -> tuple[DocumentTerm, ...]:
    if len(terms) > MAX_DOCUMENT_TERMS:
        raise SafetyError("Too many document protection terms were supplied.")
    seen = set()
    result = []
    for term in terms:
        if term.kind not in {"person", "email", "identifier", "other"}:
            raise SafetyError("Document protection term type is unsupported.")
        value = term.value
        if (
            not isinstance(value, str)
            or len(value) < 3
            or len(value) > MAX_DOCUMENT_TERM
            or value != value.strip()
            or any(ord(ch) < 32 and ch not in "\t\n\r" for ch in value)
        ):
            raise SafetyError("Document protection term is invalid.")
        if value in seen:
            continue
        seen.add(value)
        result.append(term)
    return tuple(result)


def _paragraph_texts(root: ET.Element) -> list[tuple[str, list[str]]]:
    paragraphs = []
    for paragraph in root.iter(f"{{{W}}}p"):
        texts = [
            node.text or ""
            for node in paragraph.iter()
            if node.tag == f"{{{W}}}t"
        ]
        if texts:
            paragraphs.append(("".join(texts), texts))
    return paragraphs


def _split_occurrence_exists(
    roots: list[tuple[str, ET.Element]], values: tuple[str, ...]
) -> bool:
    for _, root in roots:
        for paragraph, nodes in _paragraph_texts(root):
            for value in values:
                total = paragraph.count(value)
                direct = sum(text.count(value) for text in nodes)
                if total > direct:
                    return True
        for pattern in (EMAIL_RE, ORCID_RE):
            for paragraph, nodes in _paragraph_texts(root):
                total = len(pattern.findall(paragraph))
                direct = sum(len(pattern.findall(text)) for text in nodes)
                if total > direct:
                    return True
    return False


def _token(kind: str, used: set[str]) -> str:
    label = {
        "person": "PERSON",
        "email": "EMAIL",
        "identifier": "ID",
        "other": "TEXT",
    }[kind]
    while True:
        token = f"[SAFESET-{label}-{secrets.token_hex(4).upper()}]"
        if token not in used:
            used.add(token)
            return token


def _discover_terms(
    roots: list[tuple[str, ET.Element]], supplied: tuple[DocumentTerm, ...]
) -> tuple[DocumentTerm, ...]:
    found: list[DocumentTerm] = list(supplied)
    seen = {term.value for term in supplied}
    for _, root in roots:
        for node in root.iter(f"{{{W}}}t"):
            text = node.text or ""
            for value in EMAIL_RE.findall(text):
                if value not in seen:
                    found.append(DocumentTerm(value, "email"))
                    seen.add(value)
            for value in ORCID_RE.findall(text):
                if value not in seen:
                    found.append(DocumentTerm(value, "identifier"))
                    seen.add(value)
    return _validate_terms(tuple(found))


def _discover_relationship_terms(
    parts: dict[str, bytes], supplied: tuple[DocumentTerm, ...]
) -> tuple[DocumentTerm, ...]:
    found = list(supplied)
    seen = {term.value for term in supplied}
    relation_text = _relationship_text(parts)
    for value in EMAIL_RE.findall(relation_text):
        if value not in seen:
            found.append(DocumentTerm(value, "email"))
            seen.add(value)
    for value in ORCID_RE.findall(relation_text):
        if value not in seen:
            found.append(DocumentTerm(value, "identifier"))
            seen.add(value)
    return _validate_terms(tuple(found))


def _replace_text_and_attributes(
    roots: list[tuple[str, ET.Element]],
    parts: dict[str, bytes],
    replacements: list[dict],
) -> tuple[dict[str, bytes], list[dict]]:
    counts = {item["token"]: 0 for item in replacements}
    by_value = [(item["original"], item["token"]) for item in replacements]

    for name, root in roots:
        for node in root.iter():
            if node.tag == f"{{{W}}}t" and node.text:
                text = node.text
                for original, token in by_value:
                    occurrences = text.count(original)
                    if occurrences:
                        text = text.replace(original, token)
                        counts[token] += occurrences
                node.text = text
            for key, value in list(node.attrib.items()):
                changed = value
                for original, token in by_value:
                    occurrences = changed.count(original)
                    if occurrences:
                        changed = changed.replace(original, token)
                        counts[token] += occurrences
                if changed != value:
                    node.attrib[key] = changed
        parts[name] = _xml_bytes(root)

    for name in list(parts):
        if not name.endswith(".rels"):
            continue
        root = _parse_xml(parts[name])
        changed_any = False
        for item in root:
            for key, value in list(item.attrib.items()):
                changed = value
                for original, token in by_value:
                    occurrences = changed.count(original)
                    if occurrences:
                        changed = changed.replace(original, token)
                        counts[token] += occurrences
                if changed != value:
                    item.attrib[key] = changed
                    changed_any = True
        if changed_any:
            parts[name] = _xml_bytes(root)

    result = []
    for item in replacements:
        count = counts[item["token"]]
        if count:
            result.append({**item, "count": count})
    return parts, result


def _strip_metadata(parts: dict[str, bytes]) -> None:
    core = parts.get("docProps/core.xml")
    if core:
        root = _parse_xml(core)
        remove = {"creator", "lastModifiedBy", "revision", "created", "modified"}
        for child in list(root):
            if _local(child.tag) in remove:
                root.remove(child)
        parts["docProps/core.xml"] = _xml_bytes(root)
    app = parts.get("docProps/app.xml")
    if app:
        root = _parse_xml(app)
        for child in list(root):
            if _local(child.tag) in {"Company", "Manager"}:
                root.remove(child)
        parts["docProps/app.xml"] = _xml_bytes(root)
    _remove_package_parts(parts, {"docProps/custom.xml"})


def _remove_comment_markers(root: ET.Element) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child.tag in COMMENT_MARKER_TAGS:
                parent.remove(child)


def _remove_package_parts(parts: dict[str, bytes], removed: set[str]) -> None:
    for name in removed:
        parts.pop(name, None)

    for name in list(parts):
        if not name.endswith(".rels"):
            continue
        root = _parse_xml(parts[name])
        changed = False
        for child in list(root):
            target = child.attrib.get("Target", "").replace("\\", "/")
            if any(
                target.endswith(item.rsplit("/", 1)[-1])
                or target.lstrip("/") == item
                for item in removed
            ):
                root.remove(child)
                changed = True
        if changed:
            parts[name] = _xml_bytes(root)

    raw = parts.get("[Content_Types].xml")
    if raw:
        root = _parse_xml(raw)
        changed = False
        for child in list(root):
            part_name = child.attrib.get("PartName", "").lstrip("/")
            if part_name in removed:
                root.remove(child)
                changed = True
        if changed:
            parts["[Content_Types].xml"] = _xml_bytes(root)


def _remove_comments(parts: dict[str, bytes], roots: list[tuple[str, ET.Element]]) -> None:
    for name, root in roots:
        _remove_comment_markers(root)
        parts[name] = _xml_bytes(root)
    removed = {name for name in list(parts) if COMMENT_PART_RE.match(name)}
    _remove_package_parts(parts, removed)


def _write_parts(parts: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(parts):
            archive.writestr(name, parts[name])
    data = stream.getvalue()
    if len(data) > MAX_DOCX_BYTES:
        raise SafetyError("Protected Word document exceeds the supported size limit.")
    validate_docx_bytes(data)
    return data


def protect_document_bytes(
    source: bytes,
    terms: tuple[DocumentTerm, ...],
    *,
    remove_comments: bool = True,
) -> tuple[bytes, tuple[dict, ...], DocumentInspection]:
    parts = _read_parts(source)
    inspection = inspect_document_bytes(source)
    if inspection.tracked_changes:
        raise SafetyError("Word document contains tracked changes that must be resolved first.")
    if inspection.hidden_text:
        raise SafetyError("Word document contains hidden text that must be resolved first.")
    if inspection.embedded_objects:
        raise SafetyError("Word document contains unsupported embedded or active content.")

    roots = _text_roots(parts)
    supplied = _validate_terms(terms)
    discovered = _discover_terms(roots, supplied)
    discovered = _discover_relationship_terms(parts, discovered)
    values = tuple(term.value for term in discovered)
    if _split_occurrence_exists(roots, values):
        raise SafetyError(
            "A document identifier is split across formatted runs and cannot be protected safely."
        )

    used: set[str] = set()
    replacements = [
        {"token": _token(term.kind, used), "original": term.value, "kind": term.kind}
        for term in discovered
    ]
    parts, applied = _replace_text_and_attributes(roots, parts, replacements)
    _strip_metadata(parts)
    if remove_comments:
        _remove_comments(parts, _text_roots(parts))
    elif inspection.comments:
        raise SafetyError("Word document comments require explicit removal before protection.")

    protected = _write_parts(parts)
    protected_parts = _read_parts(protected)
    protected_text = _visible_text(_text_roots(protected_parts))
    for item in applied:
        if item["original"] in protected_text:
            raise SafetyError("A document identifier remained after protection.")
    return protected, tuple(applied), inspection


def _all_xml_text_and_attributes(parts: dict[str, bytes]) -> str:
    values = []
    for name, raw in parts.items():
        if not (name.endswith(".xml") or name.endswith(".rels")):
            continue
        root = _parse_xml(raw)
        for item in root.iter():
            if item.text:
                values.append(item.text)
            values.extend(item.attrib.values())
    return "\n".join(values)


def restore_document_bytes(returned: bytes, replacements: tuple[dict, ...]) -> bytes:
    parts = _read_parts(returned)
    inspection = inspect_document_bytes(returned)
    if inspection.tracked_changes:
        raise SafetyError("Returned Word document contains tracked changes.")
    if inspection.hidden_text:
        raise SafetyError("Returned Word document contains hidden text.")
    if inspection.embedded_objects:
        raise SafetyError("Returned Word document contains unsupported embedded or active content.")

    corpus = _all_xml_text_and_attributes(parts)
    for item in replacements:
        token = item["token"]
        expected = item["count"]
        if corpus.count(token) != expected:
            raise SafetyError("Returned Word document does not preserve every protection token.")
        if item["original"] in corpus:
            raise SafetyError("Returned Word document contains an original protected identifier.")

    pairs = [(item["token"], item["original"]) for item in replacements]
    for name in list(parts):
        if not (name.endswith(".xml") or name.endswith(".rels")):
            continue
        root = _parse_xml(parts[name])
        changed_any = False
        for node in root.iter():
            if node.text:
                changed = node.text
                for token, original in pairs:
                    changed = changed.replace(token, original)
                if changed != node.text:
                    node.text = changed
                    changed_any = True
            for key, value in list(node.attrib.items()):
                changed = value
                for token, original in pairs:
                    changed = changed.replace(token, original)
                if changed != value:
                    node.attrib[key] = changed
                    changed_any = True
        if changed_any:
            parts[name] = _xml_bytes(root)
    return _write_parts(parts)
