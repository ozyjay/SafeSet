"""Local destination guardrails and private no-clobber publication."""

import os
import stat
import tempfile
from pathlib import Path

from .errors import SafetyError
from .pseudonyms import new_id


def repository_roots(*paths: Path) -> set[Path]:
    roots = set()
    for path in (Path.cwd(), Path(__file__), *paths):
        resolved = path.expanduser().resolve()
        for parent in (resolved, *resolved.parents):
            if (parent / ".git").exists() or (
                (parent / "pyproject.toml").is_file() and (parent / "AGENTS.md").is_file()
            ):
                roots.add(parent)
    return roots


def outside_repositories(path: Path, *context: Path) -> Path:
    if os.name == "nt":
        from .windows_storage import local_path

        path = local_path(path)
    resolved = path.expanduser().resolve()
    if any(resolved.is_relative_to(root) for root in repository_roots(path, *context)):
        raise SafetyError("Operational artefacts must be stored outside repositories.")
    return resolved


def output_destination(path: Path, *context: Path) -> Path:
    resolved = outside_repositories(path, *context)
    if path.expanduser().is_symlink() or resolved.exists():
        raise SafetyError("Destination already exists; overwriting is prohibited.")
    if not resolved.parent.is_dir():
        raise SafetyError("Output directory must already exist.")
    return resolved


def default_map_path() -> Path:
    return Path.home() / ".local" / "share" / "safeset" / "maps" / f"{new_id()}.enc"


def private_directory(directory: Path, *, create: bool) -> None:
    if os.name == "nt":
        from .windows_storage import private_directory as windows_private_directory

        windows_private_directory(directory, create=create)
        return
    if os.name != "posix":
        raise SafetyError("Private mapping storage requires supported POSIX permissions.")
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise SafetyError("Mapping directory must be owned by this user with mode 0700.")


def map_destination(path: Path, export: Path, *context: Path) -> Path:
    if os.name == "nt":
        from .windows_storage import local_path

        export = local_path(export)
    resolved = outside_repositories(path, export, *context)
    export_dir = export.expanduser().resolve().parent
    if resolved.is_relative_to(export_dir) or export.resolve().is_relative_to(resolved.parent):
        raise SafetyError("Mapping and export must use separate storage directories.")
    if path.expanduser().is_symlink() or resolved.exists():
        raise SafetyError("Mapping destination already exists; overwriting is prohibited.")
    return resolved


def check_map_read(path: Path, *context: Path) -> Path:
    resolved = outside_repositories(path, *context)
    private_directory(resolved.parent, create=False)
    if os.name == "nt":
        from .windows_storage import validate_private

        validate_private(resolved, directory=False)
        return resolved
    info = resolved.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise SafetyError("Mapping must be a private regular file owned by this user (mode 0600).")
    return resolved


def publish(path: Path, data: bytes) -> None:
    """Stage privately and publish without replacing any existing destination."""
    temporary = None
    try:
        if os.name == "nt":
            from .windows_storage import local_path, private_temporary, validate_private

            path = local_path(path)
            staged = path.parent / f".safeset-{new_id()}"
            fd = private_temporary(staged)
            temporary = staged
        else:
            fd, name = tempfile.mkstemp(prefix=".safeset-", dir=path.parent)
            temporary = Path(name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "nt":
            validate_private(temporary, directory=False)
        os.link(temporary, path)
    except OSError:
        raise SafetyError("Unable to publish artefact safely; nothing was overwritten.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
