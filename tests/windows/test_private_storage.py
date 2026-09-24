"""Real Windows ACL integration tests, also runnable without pytest dependencies.

From pwsh: $env:PYTHONPATH = './src'
& ./.venv/Scripts/python.exe -m unittest discover -s tests/windows -v
All artefacts live in an automatically cleaned synthetic temporary directory.
"""

import ctypes as ct
import importlib.util
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from safeset.errors import SafetyError
from safeset.storage import (
    check_map_read,
    map_destination,
    output_destination,
    private_directory,
    publish,
)

if os.name == "nt":
    from safeset import windows_storage as win


@unittest.skipUnless(os.name == "nt", "Requires actual Windows ACL enforcement")
class WindowsStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="safeset-synthetic-acl-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.maps = self.root / "maps"
        self.exports = self.root / "exports"
        self.exports.mkdir()

    def icacls(self, path, *arguments):
        result = subprocess.run(
            ["icacls.exe", str(path), *arguments], capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, "Synthetic ACL setup failed")

    def bundle(self):
        private_directory(self.maps, create=True)
        path = self.maps / "synthetic.enc"
        # Deliberately not ciphertext: this tests storage, not encryption.
        publish(path, b"synthetic storage probe")
        return path

    def set_dacl(self, path, sddl):
        descriptor = ct.c_void_p()
        self.assertTrue(win._descriptor(sddl, 1, ct.byref(descriptor), None))
        setter = win._function(
            win._security, "SetFileSecurityW", win.wt.BOOL,
            win.wt.LPCWSTR, win.wt.DWORD, ct.c_void_p,
        )
        try:
            self.assertTrue(setter(str(path), 0x80000004, descriptor))
        finally:
            win._free(descriptor)

    def test_private_directory_creation_and_revalidation(self):
        private_directory(self.maps / "nested", create=True)
        private_directory(self.maps, create=False)
        private_directory(self.maps / "nested", create=False)
        # Independent Windows/.NET ACL inspection, without printing the owner SID.
        literal = str(self.maps).replace("'", "''")
        command = (
            f"$acl = Get-Acl -LiteralPath '{literal}'; "
            "if (-not $acl.AreAccessRulesProtected -or $acl.Access.Count -ne 1 "
            "-or $acl.Access[0].IsInherited "
            "-or $acl.Access[0].FileSystemRights -ne 'FullControl') { exit 1 }"
        )
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, "Independent ACL verification failed")

    def test_file_creation_and_subsequent_read_validation(self):
        path = self.bundle()
        self.assertEqual(check_map_read(path), path.resolve())
        self.assertEqual(path.read_bytes(), b"synthetic storage probe")
        self.assertFalse(list(self.maps.glob(".safeset-*")))

    def test_creation_does_not_repair_an_existing_broad_directory(self):
        self.maps.mkdir()
        self.icacls(self.maps, "/grant", "*S-1-1-0:(OI)(CI)(RX)")
        with self.assertRaises(SafetyError):
            private_directory(self.maps, create=True)
        self.assertEqual(list(self.maps.iterdir()), [])

    def test_rejects_explicit_everyone_read_access(self):
        path = self.bundle()
        self.icacls(path, "/grant", "*S-1-1-0:(R)")
        with self.assertRaises(SafetyError):
            check_map_read(path)

    def test_rejects_inheritance_even_from_private_parent(self):
        path = self.bundle()
        self.icacls(path, "/inheritance:e")
        with self.assertRaises(SafetyError):
            check_map_read(path)

    def test_rejects_inherited_directory_permissions(self):
        private_directory(self.maps, create=True)
        child = self.maps / "inherited"
        child.mkdir()
        with self.assertRaises(SafetyError):
            private_directory(child, create=False)

    def test_accepts_optional_system_and_administrators_only(self):
        path = self.bundle()
        sid = win._current_sid()
        self.set_dacl(path, f"D:P(A;;FA;;;{sid})(A;;FA;;;SY)(A;;FA;;;BA)")
        check_map_read(path)

    def test_rejects_null_dacl(self):
        path = self.bundle()
        self.set_dacl(path, "D:NO_ACCESS_CONTROL")
        try:
            with self.assertRaises(SafetyError):
                check_map_read(path)
        finally:
            self.set_dacl(path, f"D:P(A;;FA;;;{win._current_sid()})")

    def test_rejects_unsupported_ace(self):
        path = self.bundle()
        sid = win._current_sid()
        self.set_dacl(path, f"D:P(D;;GW;;;WD)(A;;FA;;;{sid})")
        try:
            with self.assertRaises(SafetyError):
                check_map_read(path)
        finally:
            self.set_dacl(path, f"D:P(A;;FA;;;{sid})")

    def test_rejects_multiple_hard_links(self):
        path = self.bundle()
        os.link(path, self.root / "alias.enc")
        with self.assertRaises(SafetyError):
            check_map_read(path)

    def test_rejects_junction_in_ancestry(self):
        path = self.bundle()
        junction = self.root / "junction"
        literal = str(junction).replace("'", "''")
        target = str(self.maps).replace("'", "''")
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command",
             f"New-Item -ItemType Junction -Path '{literal}' -Target '{target}' | Out-Null"],
            capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, "Synthetic junction setup failed")
        self.addCleanup(junction.rmdir)
        for operation in (
            lambda: check_map_read(junction / path.name),
            lambda: private_directory(junction, create=False),
            lambda: output_destination(junction / "new.docx"),
            lambda: publish(junction / "new.enc", b"synthetic"),
        ):
            with self.assertRaises(SafetyError):
                operation()

    def test_rejects_stream_network_and_device_paths(self):
        for path in (self.root / "probe.enc:stream", Path(r"\\server\share\probe.enc"),
                     Path(r"\\?\C:\probe.enc"), self.root / "NUL",
                     self.root / "trailing."):
            with self.assertRaises(SafetyError):
                win.local_path(path)

    def test_export_file_is_private_even_in_inheriting_directory(self):
        output = self.exports / "synthetic.docx"
        publish(output, b"synthetic export storage probe")
        win.validate_private(output, directory=False)

    def test_rejects_file_symlink(self):
        path = self.bundle()
        link = self.root / "synthetic-link.enc"
        try:
            link.symlink_to(path)
        except OSError as error:
            if error.winerror == 1314:
                self.skipTest("File symlink creation requires Developer Mode or privilege")
            raise
        with self.assertRaises(SafetyError):
            check_map_read(link)

    def test_rejects_wrong_owner_when_privilege_available(self):
        path = self.bundle()
        changed = subprocess.run(
            ["icacls.exe", str(path), "/setowner", "*S-1-5-32-544"],
            capture_output=True, timeout=20,
        )
        if changed.returncode:
            self.skipTest("Changing owner to Administrators requires additional privilege")
        try:
            with self.assertRaises(SafetyError):
                check_map_read(path)
        finally:
            self.icacls(path, "/setowner", "*" + win._current_sid())

    def test_staged_file_creation_never_overwrites(self):
        path = self.bundle()
        with self.assertRaises(SafetyError):
            win.private_temporary(path)
        self.assertEqual(path.read_bytes(), b"synthetic storage probe")

    def test_api_creation_failure_writes_nothing(self):
        with patch.object(win, "_create_file", return_value=win.INVALID_HANDLE):
            with self.assertRaises(SafetyError):
                publish(self.exports / "synthetic.docx", b"synthetic")
        self.assertEqual(list(self.exports.iterdir()), [])

    def test_errors_do_not_include_paths_or_native_details(self):
        self.maps.mkdir()
        with self.assertRaises(SafetyError) as caught:
            private_directory(self.maps, create=False)
        self.assertEqual(str(caught.exception), win.PERMISSIONS_ERROR)

    def test_no_clobber_preserves_existing_bytes(self):
        path = self.bundle()
        with self.assertRaises(SafetyError):
            publish(path, b"synthetic replacement")
        self.assertEqual(path.read_bytes(), b"synthetic storage probe")
        self.assertFalse(list(self.maps.glob(".safeset-*")))

    def test_rejects_repository_destinations(self):
        repo = self.root / "synthetic-repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        with self.assertRaises(SafetyError):
            output_destination(repo / "out.docx")
        with self.assertRaises(SafetyError):
            map_destination(repo / "bundle.enc", self.exports / "out.docx")

    def test_map_and_export_must_be_separate(self):
        for path in (self.exports / "probe.enc", self.exports / "nested/probe.enc",
                     self.root / "probe.enc"):
            with self.assertRaises(SafetyError):
                map_destination(path, self.exports / "out.docx")
        self.assertEqual(
            map_destination(self.maps / "probe.enc", self.exports / "out.docx"),
            self.maps / "probe.enc",
        )

    def test_no_network_needed_for_storage(self):
        with patch.object(socket, "socket", side_effect=AssertionError("Network attempted")):
            check_map_read(self.bundle())

    def test_native_security_query_failure_is_closed(self):
        path = self.bundle()
        with patch.object(win, "_get_security", return_value=5):
            with self.assertRaises(SafetyError):
                check_map_read(path)

    @unittest.skipUnless(
        all(importlib.util.find_spec(name) for name in ("cryptography", "openpyxl", "yaml")),
        "Encrypted DOCX integration requires unavailable Python dependencies",
    )
    def test_encrypted_document_round_trip(self):
        import io
        import zipfile

        from safeset.document import DocumentTerm
        from safeset.document_flow import (
            approve_document_protection,
            approve_document_restoration,
            prepare_document_protection,
            prepare_document_restoration,
        )

        source = self.root / "synthetic.docx"
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("[Content_Types].xml", '<Types xmlns="urn:synthetic"/>')
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
                '2006/main"><w:body><w:p><w:r><w:t>Synthetic Researcher</w:t>'
                '</w:r></w:p></w:body></w:document>',
            )
        source.write_bytes(data.getvalue())
        output = self.exports / "protected.docx"
        bundle = self.maps / "document.enc"
        restored = self.root / "restored.docx"
        passphrase = "synthetic-only-never-reuse-this-passphrase"
        with patch.object(socket, "socket", side_effect=AssertionError("Network attempted")):
            review = prepare_document_protection(
                source, (DocumentTerm("Synthetic Researcher", "person"),), output, bundle,
            )
            self.assertFalse(output.exists())
            approve_document_protection(review, passphrase, approved=True)
            check_map_read(bundle)
            self.assertNotIn(b"Synthetic Researcher", bundle.read_bytes())
            review = prepare_document_restoration(output, bundle, restored, passphrase)
            approve_document_restoration(review, authorised=True)
        with zipfile.ZipFile(restored) as archive:
            self.assertIn(b"Synthetic Researcher", archive.read("word/document.xml"))


if __name__ == "__main__":
    unittest.main()
