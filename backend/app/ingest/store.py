"""Immutable local object store using application-generated keys only."""

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from backend.app.core.errors import PlatformError

_KEY = re.compile(r"[A-Za-z0-9_./-]{1,255}")


class ArtifactStore(Protocol):
    def put(self, data: bytes, key: str) -> str: ...
    def read(self, key: str) -> bytes: ...


class LocalArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, key: str) -> Path:
        if not _KEY.fullmatch(key) or key.startswith("/") or any(part in {"", ".", ".."} for part in key.split("/")):
            raise PlatformError("INVALID_STORAGE_KEY", "Invalid object storage key", 400)
        target = self.root.joinpath(*key.split("/"))
        if not target.is_relative_to(self.root):
            raise PlatformError("INVALID_STORAGE_KEY", "Invalid object storage key", 400)
        current = self.root
        for part in key.split("/"):
            current = current / part
            if current.is_symlink() or (current.exists() and current.resolve() != current):
                raise PlatformError("INVALID_STORAGE_KEY", "Object path contains a link", 400)
        return target

    def put(self, data: bytes, key: str) -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Check again after creating trusted storage ancestors.
        target = self._path(key)
        if target.exists():
            if target.is_file() and target.read_bytes() == data:
                return key
            raise PlatformError("ARTIFACT_CONFLICT", "Immutable object already contains different data", 409)
        temporary: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=target.parent)
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(data)
                destination.flush()
                os.fsync(destination.fileno())
            try:
                # Atomic publication without replacing an existing immutable object.
                # Windows rename rejects existing targets; POSIX rename replaces
                # them, so POSIX uses an atomic create-only hard link instead.
                if os.name == "nt":
                    os.rename(temporary, target)
                    temporary = None
                else:
                    os.link(temporary, target)
            except (FileExistsError, PermissionError):
                # Windows may return ACCESS_DENIED when the winning publisher
                # has already marked the existing target read-only.
                if not target.exists():
                    raise
                if target.is_symlink() or not target.is_file() or target.read_bytes() != data:
                    raise PlatformError("ARTIFACT_CONFLICT", "Immutable object already contains different data", 409) from None
            if temporary is not None:
                temporary.unlink()
                temporary = None
            target.chmod(0o444)
            return key
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def read(self, key: str) -> bytes:
        target = self._path(key)
        if not target.is_file():
            raise PlatformError("ARTIFACT_NOT_FOUND", "Stored object does not exist", 404)
        return target.read_bytes()
