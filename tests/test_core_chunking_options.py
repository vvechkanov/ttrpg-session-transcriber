"""Unit tests for ``core.chunking.ChunkingOptions`` dataclass contract.

The options dataclass is the bridge between UI preferences and the
pipeline post-step. It must be frozen, carry the documented defaults,
and survive equality / hashing (used for caching pipeline configs).
"""

from __future__ import annotations

import pytest


class TestChunkingOptionsDefaults:
    def test_default_enabled_is_false(self):
        from core.chunking import ChunkingOptions
        opts = ChunkingOptions()
        assert opts.enabled is False

    def test_default_chunk_chars(self):
        from core.chunking import ChunkingOptions
        opts = ChunkingOptions()
        assert opts.chunk_chars == 40_000

    def test_default_overlap_ratio(self):
        from core.chunking import ChunkingOptions
        opts = ChunkingOptions()
        assert opts.overlap_ratio == pytest.approx(0.20)


class TestChunkingOptionsFrozen:
    def test_is_frozen(self):
        from core.chunking import ChunkingOptions
        opts = ChunkingOptions()
        with pytest.raises((AttributeError, TypeError)):
            opts.enabled = True  # type: ignore[misc]

    def test_equality(self):
        from core.chunking import ChunkingOptions
        a = ChunkingOptions(enabled=True, chunk_chars=30_000, overlap_ratio=0.1)
        b = ChunkingOptions(enabled=True, chunk_chars=30_000, overlap_ratio=0.1)
        assert a == b

    def test_hashable(self):
        from core.chunking import ChunkingOptions
        opts = ChunkingOptions(enabled=True)
        {opts}  # does not raise
