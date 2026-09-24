"""Synthetic DOCX protection/restoration tests."""

import io
import socket
import zipfile
from pathlib import Path

import pytest

from safeset.document import DocumentTerm, inspect_document
from safeset.document_flow import (
    approve_document_protection,
    approve_document_restoration,
    prepare_document_protection,
    prepare_document_restoration,
)
from safeset.errors import SafetyError

from .conftest import PASSPHRASE

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_bytes(
    body: str,
    *,
    comments: bool = False,
    tracked: bool = False,
    hidden: bool = False,
) -> bytes:
    if tracked:
        body_xml = (
            f'<w:p><w:ins w:id="1" w:author="Synthetic Author">'
            f'<w:r><w:t>{body}</w:t></w:r></w:ins></w:p>'
        )
    elif hidden:
        body_xml = (
            f'<w:p><w:r><w:rPr><w:vanish/></w:rPr><w:t>{body}</w:t></w:r></w:p>'
        )
    else:
        body_xml = body
    comment_marker = (
        '<w:commentRangeStart w:id="0"/><w:commentRangeEnd w:id="0"/>'
        '<w:r><w:commentReference w:id="0"/></w:r>'
        if comments
        else ""
    )
    document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}">
  <w:body>{body_xml}{comment_marker}<w:sectPr/></w:body>
</w:document>'''.encode()
    content_types = b'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="xml" ContentType="application/xml"/>
 <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
 <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
 <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
 <Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>
 <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>'''
    root_rels = b'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
 <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
 <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
 <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/>
</Relationships>'''
    document_rels = b'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="mailto:student@example.test" TargetMode="External"/>
 <Relationship Id="rId10" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>
</Relationships>'''
    core = b'''<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/">
 <dc:creator>Synthetic Student</dc:creator>
 <cp:lastModifiedBy>Synthetic Supervisor</cp:lastModifiedBy>
 <cp:revision>42</cp:revision>
 <dcterms:created>2026-09-24T00:00:00Z</dcterms:created>
</cp:coreProperties>'''
    app = b'''<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
 <Company>Synthetic University</Company><Manager>Synthetic Supervisor</Manager>
</Properties>'''
    custom = b'''<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties">
 <property name="SyntheticPrivateProperty"/>
</Properties>'''
    comment_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="{W}">
 <w:comment w:id="0" w:author="Synthetic Student"><w:p><w:r><w:t>Private comment</w:t></w:r></w:p></w:comment>
</w:comments>'''.encode()

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("docProps/custom.xml", custom)
        if comments:
            archive.writestr("word/comments.xml", comment_xml)
    return stream.getvalue()


def text_parts(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        return "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist()
            if name.endswith(".xml") or name.endswith(".rels")
        )


def destinations(tmp_path: Path):
    for name in ("maps", "exports", "private"):
        (tmp_path / name).mkdir(mode=0o700)
    return (
        tmp_path / "exports/protected.docx",
        tmp_path / "maps/document.enc",
        tmp_path / "private/restored.docx",
    )


def test_document_round_trip_removes_metadata_comments_and_restores_terms(tmp_path, monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("Network access attempted")

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)

    source = tmp_path / "draft.docx"
    source.write_bytes(
        docx_bytes(
            '<w:p><w:r><w:t>Synthetic Student</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>student@example.test</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>0000-0002-1825-0097</w:t></w:r></w:p>',
            comments=True,
        )
    )
    protected, bundle, restored = destinations(tmp_path)
    inspection = inspect_document(source)
    assert inspection.email_count == 1
    assert inspection.orcid_count == 1
    assert inspection.comments == 1
    assert inspection.metadata_fields >= 2

    review = prepare_document_protection(
        source,
        (DocumentTerm("Synthetic Student", "person"),),
        protected,
        bundle,
        remove_comments=True,
    )
    assert review.replacement_count == 3
    assert review.replacement_occurrences >= 4
    assert review.comments_removed
    approve_document_protection(review, PASSPHRASE, approved=True)

    protected_xml = text_parts(protected.read_bytes())
    assert "Synthetic Student" not in protected_xml
    assert "student@example.test" not in protected_xml
    assert "0000-0002-1825-0097" not in protected_xml
    assert "Private comment" not in protected_xml
    assert "Synthetic University" not in protected_xml
    assert "lastModifiedBy" not in protected_xml
    assert "custom.xml" not in protected_xml

    returned = tmp_path / "returned.docx"
    returned.write_bytes(protected.read_bytes())
    restore_review = prepare_document_restoration(returned, bundle, restored, PASSPHRASE)
    assert restore_review.replacement_count == 3
    approve_document_restoration(restore_review, authorised=True)

    restored_xml = text_parts(restored.read_bytes())
    assert "Synthetic Student" in restored_xml
    assert "student@example.test" in restored_xml
    assert "0000-0002-1825-0097" in restored_xml
    assert "Private comment" not in restored_xml
    assert "Synthetic University" not in restored_xml


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"tracked": True}, "tracked changes"),
        ({"hidden": True}, "hidden text"),
    ],
)
def test_document_protection_blocks_unsupported_authoring_state(tmp_path, kwargs, message):
    source = tmp_path / "draft.docx"
    source.write_bytes(docx_bytes("Synthetic text", **kwargs))
    protected, bundle, _ = destinations(tmp_path)
    with pytest.raises(SafetyError, match=message):
        prepare_document_protection(source, (), protected, bundle)


def test_document_protection_blocks_split_identity_across_runs(tmp_path):
    source = tmp_path / "draft.docx"
    source.write_bytes(
        docx_bytes(
            '<w:p><w:r><w:t>Synthetic </w:t></w:r>'
            '<w:r><w:t>Student</w:t></w:r></w:p>'
        )
    )
    protected, bundle, _ = destinations(tmp_path)
    with pytest.raises(SafetyError, match="split across formatted runs"):
        prepare_document_protection(
            source,
            (DocumentTerm("Synthetic Student", "person"),),
            protected,
            bundle,
        )


def test_document_restoration_rejects_missing_or_duplicated_token(tmp_path):
    source = tmp_path / "draft.docx"
    source.write_bytes(
        docx_bytes('<w:p><w:r><w:t>Synthetic Student</w:t></w:r></w:p>')
    )
    protected, bundle, restored = destinations(tmp_path)
    review = prepare_document_protection(
        source,
        (DocumentTerm("Synthetic Student", "person"),),
        protected,
        bundle,
    )
    approve_document_protection(review, PASSPHRASE, approved=True)
    data = protected.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    document = parts["word/document.xml"].decode()
    token_start = document.index("[SAFESET-")
    token_end = document.index("]", token_start) + 1
    token = document[token_start:token_end]
    parts["word/document.xml"] = document.replace(token, "").encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in parts.items():
            archive.writestr(name, raw)
    returned = tmp_path / "returned.docx"
    returned.write_bytes(stream.getvalue())

    with pytest.raises(SafetyError, match="preserve every protection token"):
        prepare_document_restoration(returned, bundle, restored, PASSPHRASE)
