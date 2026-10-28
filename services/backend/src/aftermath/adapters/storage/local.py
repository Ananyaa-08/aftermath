import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from aftermath.core.errors import DomainError
from aftermath.core.text import bytes_hash


class LocalObjectStore:
    """Content-addressed development storage. Orphans are safe; metadata commits in PostgreSQL."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def _path(self, workspace_id: UUID, key: str) -> Path:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", key):
            raise DomainError("INVALID_OBJECT_KEY", "Invalid content-addressed object key")
        path = self.root / str(workspace_id) / key[7:]
        if (
            not path.resolve().is_relative_to(self.root)
            or path.is_symlink()
            or path.parent.is_symlink()
        ):
            raise DomainError("UNSAFE_OBJECT_PATH", "Object path is unsafe")
        return path

    def get(self, workspace_id: UUID, key: str) -> bytes:
        path = self._path(workspace_id, key)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                data = stream.read()
        except OSError:
            raise DomainError("OBJECT_UNAVAILABLE", "Source object is unavailable", 503) from None
        if bytes_hash(data) != key:
            raise DomainError("OBJECT_CORRUPT", "Source object failed hash verification", 503)
        return data

    def put(self, workspace_id: UUID, key: str, data: bytes) -> None:
        if bytes_hash(data) != key:
            raise DomainError("OBJECT_HASH_MISMATCH", "Source object hash mismatch")
        path = self._path(workspace_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if self.get(workspace_id, key) != data:
                raise DomainError("OBJECT_CORRUPT", "Stored bytes do not match", 503)
            return
        fd, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(
                    temporary, path
                )  # publish complete bytes without overwriting a concurrent writer
            except FileExistsError:
                self.get(workspace_id, key)
        finally:
            os.unlink(temporary)
