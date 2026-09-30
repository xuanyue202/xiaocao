"""Durable atomic publication for mutable files and immutable evidence."""
from __future__ import annotations

import errno
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, data: bytes, *, immutable: bool = False) -> None:
    """Durable file publication; an immutable conflict never overwrites evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise ValueError("IMMUTABLE_FILE_CONTENT_CONFLICT")
        else:
            os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            try:
                os.fsync(directory)
            except OSError as exc:
                if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
                    raise
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
