"""Short-lived, on-disk store for generated artifacts.

The service is stateless by design: a caller uploads a profile, receives a run
id, and downloads the ``.tex``/``.pdf``/``.json`` for that run. Nothing is kept
beyond the TTL, which matters because the payloads are people's resumes.
"""

from __future__ import annotations

import logging
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_ARTIFACT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ArtifactNotFoundError(KeyError):
    """Raised when a run or artifact does not exist, or has expired."""


@dataclass(frozen=True)
class StoredArtifact:
    run_id: str
    name: str
    path: Path
    media_type: str


_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".tex": "application/x-tex",
    ".json": "application/json",
    ".log": "text/plain; charset=utf-8",
}


class ArtifactStore:
    """A TTL-expiring directory of per-run artifacts."""

    def __init__(self, root: Path, *, ttl_seconds: int = 1800) -> None:
        self._root = Path(root)
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    @staticmethod
    def new_run_id() -> str:
        return uuid.uuid4().hex

    def write(self, run_id: str, name: str, data: bytes | str) -> StoredArtifact:
        """Persist one artifact for ``run_id``."""
        path = self._resolve(run_id, name, must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_bytes(data)

        return StoredArtifact(
            run_id=run_id,
            name=name,
            path=path,
            media_type=_MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
        )

    def read(self, run_id: str, name: str) -> StoredArtifact:
        """Fetch one artifact, refusing anything past its TTL."""
        path = self._resolve(run_id, name, must_exist=True)

        if self._age_seconds(path.parent) > self._ttl_seconds:
            self._remove(path.parent)
            raise ArtifactNotFoundError(f"Run {run_id!r} has expired.")

        return StoredArtifact(
            run_id=run_id,
            name=name,
            path=path,
            media_type=_MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
        )

    def delete_run(self, run_id: str) -> None:
        self._remove(self._run_dir(run_id))

    def sweep(self) -> int:
        """Delete every expired run. Returns how many were removed."""
        removed = 0

        with self._lock:
            for child in self._root.iterdir():
                if not child.is_dir():
                    continue
                if self._age_seconds(child) > self._ttl_seconds:
                    shutil.rmtree(child, ignore_errors=True)
                    removed += 1

        if removed:
            logger.info("Swept %s expired run(s).", removed)

        return removed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_dir(self, run_id: str) -> Path:
        if not _RUN_ID_PATTERN.match(run_id):
            raise ArtifactNotFoundError(f"Invalid run id: {run_id!r}")
        return self._root / run_id

    def _resolve(self, run_id: str, name: str, *, must_exist: bool) -> Path:
        # The pattern excludes separators, and the dot-only check excludes
        # "." and ".." which the pattern would otherwise admit.
        if not _ARTIFACT_NAME_PATTERN.match(name) or name.strip(".") == "":
            raise ArtifactNotFoundError(f"Invalid artifact name: {name!r}")

        path = self._run_dir(run_id) / name

        # Belt and braces: the patterns above already exclude separators and
        # `..`, but resolve and re-check so no future change can regress into
        # a traversal.
        resolved_root = self._root.resolve()
        resolved = path.resolve() if path.exists() else (resolved_root / run_id / name)

        if not resolved.is_relative_to(resolved_root):
            raise ArtifactNotFoundError(f"Invalid artifact path: {run_id}/{name}")

        if must_exist and not path.is_file():
            raise ArtifactNotFoundError(f"No artifact {name!r} for run {run_id!r}.")

        return path

    @staticmethod
    def _age_seconds(path: Path) -> float:
        try:
            return max(0.0, time.time() - path.stat().st_mtime)
        except FileNotFoundError:
            return float("inf")

    @staticmethod
    def _remove(path: Path) -> None:
        shutil.rmtree(path, ignore_errors=True)
