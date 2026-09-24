"""Restricted local NTFS storage using Win32, with no shell or third-party binding.

Imported only on Windows. All public failures are fixed, value-free SafetyErrors.
Existing ACLs are validated, never repaired. Administrators/SYSTEM and hostile
same-account processes are outside this boundary, as described in the threat model.
"""

import ctypes as ct
import os
import stat
from contextlib import contextmanager
from ctypes import wintypes as wt
from pathlib import Path

from .errors import SafetyError

PERMISSIONS_ERROR = "Windows private storage permissions could not be verified."
PATH_ERROR = "Windows storage requires a local fixed NTFS path without reparse points."
PUBLICATION_ERROR = "Unable to publish artefact safely; nothing was overwritten."

READ_CONTROL = 0x20000
FILE_READ_ATTRIBUTES = 0x80
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ALL_ACCESS = 0x1F01FF
SE_DACL_PROTECTED = 0x1000
INVALID_HANDLE = ct.c_void_p(-1).value


class SecurityAttributes(ct.Structure):
    _fields_ = [("length", wt.DWORD), ("descriptor", ct.c_void_p), ("inherit", wt.BOOL)]


class Acl(ct.Structure):
    _fields_ = [
        ("revision", wt.BYTE), ("reserved", wt.BYTE), ("size", wt.WORD),
        ("count", wt.WORD), ("reserved2", wt.WORD),
    ]


class AceHeader(ct.Structure):
    _fields_ = [("type", wt.BYTE), ("flags", wt.BYTE), ("size", wt.WORD)]


class FileInformation(ct.Structure):
    _fields_ = [
        ("attributes", wt.DWORD), ("created", wt.FILETIME),
        ("accessed", wt.FILETIME), ("modified", wt.FILETIME),
        ("volume", wt.DWORD), ("size_high", wt.DWORD), ("size_low", wt.DWORD),
        ("links", wt.DWORD), ("index_high", wt.DWORD), ("index_low", wt.DWORD),
    ]


def _function(dll, name, result, *arguments):
    function = getattr(dll, name)
    function.restype = result
    function.argtypes = arguments
    return function


_kernel = ct.WinDLL("kernel32", use_last_error=True)
_security = ct.WinDLL("advapi32", use_last_error=True)
_ptr = ct.c_void_p
_out = ct.POINTER(_ptr)
_close = _function(_kernel, "CloseHandle", wt.BOOL, wt.HANDLE)
_free = _function(_kernel, "LocalFree", _ptr, _ptr)
_process = _function(_kernel, "GetCurrentProcess", wt.HANDLE)
_open_token = _function(_security, "OpenProcessToken", wt.BOOL, wt.HANDLE, wt.DWORD, _out)
_token_info = _function(
    _security, "GetTokenInformation", wt.BOOL,
    wt.HANDLE, ct.c_int, _ptr, wt.DWORD, ct.POINTER(wt.DWORD),
)
_sid_string = _function(_security, "ConvertSidToStringSidW", wt.BOOL, _ptr, _out)
_descriptor = _function(
    _security, "ConvertStringSecurityDescriptorToSecurityDescriptorW", wt.BOOL,
    wt.LPCWSTR, wt.DWORD, _out, ct.POINTER(wt.DWORD),
)
_get_security = _function(
    _security, "GetSecurityInfo", wt.DWORD,
    wt.HANDLE, ct.c_int, wt.DWORD, _out, _out, _out, _out, _out,
)
_get_control = _function(
    _security, "GetSecurityDescriptorControl", wt.BOOL,
    _ptr, ct.POINTER(wt.WORD), ct.POINTER(wt.DWORD),
)
_valid_acl = _function(_security, "IsValidAcl", wt.BOOL, _ptr)
_get_ace = _function(_security, "GetAce", wt.BOOL, _ptr, wt.DWORD, _out)
_create_directory = _function(
    _kernel, "CreateDirectoryW", wt.BOOL, wt.LPCWSTR, ct.POINTER(SecurityAttributes),
)
_create_file = _function(
    _kernel, "CreateFileW", wt.HANDLE, wt.LPCWSTR, wt.DWORD, wt.DWORD,
    ct.POINTER(SecurityAttributes), wt.DWORD, wt.DWORD, wt.HANDLE,
)
_file_info = _function(
    _kernel, "GetFileInformationByHandle", wt.BOOL, wt.HANDLE, ct.POINTER(FileInformation),
)
_drive_type = _function(_kernel, "GetDriveTypeW", wt.UINT, wt.LPCWSTR)
_volume_path = _function(
    _kernel, "GetVolumePathNameW", wt.BOOL, wt.LPCWSTR, wt.LPWSTR, wt.DWORD,
)
_volume_info = _function(
    _kernel, "GetVolumeInformationW", wt.BOOL, wt.LPCWSTR, wt.LPWSTR, wt.DWORD,
    ct.POINTER(wt.DWORD), ct.POINTER(wt.DWORD), ct.POINTER(wt.DWORD), wt.LPWSTR, wt.DWORD,
)


def _require(ok, message=PERMISSIONS_ERROR):
    if not ok:
        raise SafetyError(message)


def _sid_text(sid) -> str:
    result = _ptr()
    _require(_sid_string(sid, ct.byref(result)))
    try:
        return ct.wstring_at(result)
    finally:
        _free(result)


def _current_sid() -> str:
    token = _ptr()
    _require(_open_token(_process(), 0x0008, ct.byref(token)))  # TOKEN_QUERY
    try:
        size = wt.DWORD()
        _token_info(token, 1, None, 0, ct.byref(size))  # TokenUser
        _require(0 < size.value <= 65536)
        buffer = ct.create_string_buffer(size.value)
        _require(_token_info(token, 1, buffer, size, ct.byref(size)))
        return _sid_text(ct.cast(buffer, ct.POINTER(_ptr))[0])
    finally:
        _close(token)


@contextmanager
def _private_attributes(*, directory: bool):
    sid = _current_sid()
    flags = "OICI" if directory else ""
    # P disables inheritance. Only the current user is granted access at creation.
    sddl = f"O:{sid}D:P(A;{flags};FA;;;{sid})"
    descriptor = _ptr()
    _require(_descriptor(sddl, 1, ct.byref(descriptor), None))
    try:
        yield SecurityAttributes(ct.sizeof(SecurityAttributes), descriptor, False)
    finally:
        _free(descriptor)


def local_path(path: Path) -> Path:
    """Check the lexical path before resolving, so junctions cannot disappear."""
    try:
        expanded = path.expanduser()
        # Reject ambiguous Win32 spellings, streams and device/UNC namespaces.
        _require(not str(expanded).startswith(("\\\\", "//")), PATH_ERROR)
        _require(not expanded.drive or expanded.is_absolute(), PATH_ERROR)
        _require(not expanded.is_reserved(), PATH_ERROR)
        for part in expanded.parts[1:] if expanded.anchor else expanded.parts:
            _require(
                part not in {".", ".."} and ":" not in part
                and not part.endswith((".", " ")) and not any(ord(c) < 32 for c in part),
                PATH_ERROR,
            )
        absolute = expanded.absolute()
        existing = None
        for component in (*reversed(absolute.parents), absolute):
            try:
                info = component.lstat()
            except FileNotFoundError:
                continue
            _require(not info.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT, PATH_ERROR)
            existing = component
        _require(existing is not None, PATH_ERROR)
        volume = ct.create_unicode_buffer(32768)
        _require(_volume_path(str(existing), volume, len(volume)), PATH_ERROR)
        _require(_drive_type(volume.value) == 3, PATH_ERROR)  # DRIVE_FIXED
        filesystem = ct.create_unicode_buffer(32)
        flags = wt.DWORD()
        _require(
            _volume_info(volume.value, None, 0, None, None, ct.byref(flags),
                         filesystem, len(filesystem)),
            PATH_ERROR,
        )
        _require(filesystem.value == "NTFS" and flags.value & 0x8, PATH_ERROR)
        return absolute
    except OSError:
        raise SafetyError(PATH_ERROR) from None


def _validate_handle(handle, *, directory: bool) -> None:
    info = FileInformation()
    _require(_file_info(handle, ct.byref(info)))
    _require(not info.attributes & FILE_ATTRIBUTE_REPARSE_POINT)
    _require(bool(info.attributes & 0x10) == directory)  # FILE_ATTRIBUTE_DIRECTORY
    _require(directory or info.links == 1)
    owner, dacl, descriptor = _ptr(), _ptr(), _ptr()
    _require(_get_security(handle, 1, 0x5, ct.byref(owner), None,
                           ct.byref(dacl), None, ct.byref(descriptor)) == 0)
    try:
        sid = _current_sid()
        _require(owner and _sid_text(owner) == sid and dacl)
        control, revision = wt.WORD(), wt.DWORD()
        _require(_get_control(descriptor, ct.byref(control), ct.byref(revision)))
        _require(control.value & SE_DACL_PROTECTED and _valid_acl(dacl))
        acl = ct.cast(dacl, ct.POINTER(Acl)).contents
        _require(1 <= acl.count <= 3)
        principals = set()
        for index in range(acl.count):
            ace = _ptr()
            _require(_get_ace(dacl, index, ct.byref(ace)))
            header = ct.cast(ace, ct.POINTER(AceHeader)).contents
            # Only a simple explicit ACCESS_ALLOWED_ACE is supported.
            _require(header.type == 0 and header.size >= 16)
            _require(header.flags in ({0, 3} if directory else {0}))
            mask = wt.DWORD.from_address(ace.value + 4).value
            _require(mask == FILE_ALL_ACCESS)
            principal = _sid_text(ace.value + 8)
            _require(principal in {sid, "S-1-5-18", "S-1-5-32-544"})
            _require(principal not in principals)
            principals.add(principal)
        _require(sid in principals)
    finally:
        _free(descriptor)


def validate_private(path: Path, *, directory: bool) -> None:
    path = local_path(path)
    try:
        info = path.lstat()
        _require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        _require(directory or info.st_nlink == 1)
        handle = _create_file(
            str(path), READ_CONTROL | FILE_READ_ATTRIBUTES, 1, None, 3,
            FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, None,
        )
        _require(handle != INVALID_HANDLE)
        try:
            _validate_handle(handle, directory=directory)
        finally:
            _close(handle)
    except OSError:
        raise SafetyError(PERMISSIONS_ERROR) from None


def private_directory(path: Path, *, create: bool) -> None:
    path = local_path(path)
    try:
        if create and not path.exists():
            if not path.parent.exists():
                private_directory(path.parent, create=True)
            with _private_attributes(directory=True) as attributes:
                if not _create_directory(str(path), ct.byref(attributes)):
                    # A concurrent creation is acceptable only after full validation.
                    _require(ct.get_last_error() == 183)
        validate_private(path, directory=True)
    except OSError:
        raise SafetyError(PERMISSIONS_ERROR) from None


def private_temporary(path: Path) -> int:
    """Exclusively create a protected file and return its owned Python descriptor."""
    import msvcrt

    path = local_path(path)
    with _private_attributes(directory=False) as attributes:
        handle = _create_file(
            str(path), 0x40000000 | READ_CONTROL, 0, ct.byref(attributes), 1,
            FILE_FLAG_OPEN_REPARSE_POINT, None,
        )  # GENERIC_WRITE, no sharing, CREATE_NEW
    _require(handle != INVALID_HANDLE, PUBLICATION_ERROR)
    try:
        _validate_handle(handle, directory=False)
        fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
    except BaseException:
        _close(handle)
        # Empty exclusive file may remain if validation failed; never write to it.
        raise
    return fd
