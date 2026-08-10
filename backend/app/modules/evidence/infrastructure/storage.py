"""Safe local evidence storage; original names never control filesystem paths."""
from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.config import Settings
from app.shared.exceptions import ValidationError


@dataclass(frozen=True)
class StoredEvidence:
    storage_key: str
    sha256: str
    byte_size: int


class EvidenceStorage:
    def __init__(self, settings: Settings):
        self.root = Path(settings.EVIDENCE_STORAGE_DIR).resolve()
        self.max_bytes = settings.MAX_EVIDENCE_BYTES

    def _path(self, storage_key: str) -> Path:
        if not storage_key or any(c not in "0123456789abcdef" for c in storage_key) or len(storage_key) != 32:
            raise ValidationError("Invalid evidence storage key.")
        path = (self.root / storage_key).resolve()
        if path.parent != self.root:
            raise ValidationError("Unsafe evidence storage path.")
        return path

    def store_stream(self, stream: BinaryIO) -> StoredEvidence:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        storage_key = secrets.token_hex(16)
        destination = self._path(storage_key)
        digest = hashlib.sha256()
        size = 0
        try:
            with destination.open("xb") as output:
                while True:
                    chunk = stream.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ValidationError(f"Evidence exceeds the {self.max_bytes}-byte limit.")
                    digest.update(chunk)
                    output.write(chunk)
            if size == 0:
                raise ValidationError("Evidence files cannot be empty.")
            return StoredEvidence(storage_key=storage_key, sha256=digest.hexdigest(), byte_size=size)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def open_for_read(self, storage_key: str) -> BinaryIO:
        path = self._path(storage_key)
        try:
            return path.open("rb")
        except FileNotFoundError as exc:
            raise ValidationError("Evidence bytes are unavailable.") from exc

    def delete(self, storage_key: str) -> None:
        self._path(storage_key).unlink(missing_ok=True)
