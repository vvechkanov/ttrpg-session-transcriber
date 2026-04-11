"""Disk-cached Source decorator (infrastructure primitive).

Scaffolding for P3: class exists to reserve the interface but is NOT wired
into ``pipeline.run()`` in P2. ``_load``/``_save`` raise ``NotImplementedError``.
"""

from __future__ import annotations

from pathlib import Path

from domain.annotations import Annotation
from sources.base import Source


class DiskCachedSource(Source):
    """Декоратор: кэширует extract() на диск. НЕ используется в P2 pipeline."""

    name = "disk-cached"

    def __init__(self, wrapped: Source, cache_dir: Path) -> None:
        self.wrapped = wrapped
        self.cache_dir = cache_dir

    def extract(self, session_dir: Path) -> list[Annotation]:
        cache_file = self.cache_dir / f"{self.wrapped.name}.json"
        if cache_file.exists():
            return self._load(cache_file)
        annotations = self.wrapped.extract(session_dir)
        self._save(annotations, cache_file)
        return annotations

    def _load(self, path: Path) -> list[Annotation]:
        """Load cached annotations from JSON.

        JSON schema: ``{"schema_version": 1, "source": <name>, "annotations": [...]}``.
        Each annotation carries a type discriminator used to pick the right dataclass.
        """
        raise NotImplementedError("DiskCachedSource P2 stub — wire up in P3")

    def _save(self, annotations: list[Annotation], path: Path) -> None:
        """Persist annotations to JSON under schema v1."""
        raise NotImplementedError("DiskCachedSource P2 stub — wire up in P3")
