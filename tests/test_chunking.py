"""Unit tests for ``core.chunking.format_context`` speaker_map rendering.

``format_context`` reads ``speaker_map.json`` raw (no normalization pass)
and must tolerate both the new ``characters: [...]`` list shape and the
legacy ``character: "..."`` single string shape in the same rendering
path.
"""

from __future__ import annotations

import json


class TestFormatContextSpeakerMap:
    def test_new_shape_single_character(self, tmp_path):
        from core.chunking import format_context

        data = {
            "1-pc": {
                "player": "Alice",
                "characters": ["Aragorn"],
                "role": "PC",
            },
        }
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        merged = tmp_path / "merged.txt"
        merged.write_text("Alice (Aragorn): hello\n", encoding="utf-8")

        out = format_context(tmp_path, merged, "Alice (Aragorn): hello\n")

        assert "- 1-pc: Alice / Aragorn [PC]" in out

    def test_new_shape_multi_character_joined(self, tmp_path):
        from core.chunking import format_context

        data = {
            "1-pc": {
                "player": "Alice",
                "characters": ["Одетт", "Lyra"],
                "role": "PC",
            },
        }
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        merged = tmp_path / "merged.txt"
        merged.write_text("irrelevant\n", encoding="utf-8")

        out = format_context(tmp_path, merged, "irrelevant\n")

        # Characters joined with " / ", then prefixed by player + " / ".
        assert "- 1-pc: Alice / Одетт / Lyra [PC]" in out

    def test_new_shape_gm_empty_characters(self, tmp_path):
        from core.chunking import format_context

        data = {"1-gm": {"player": "GM", "characters": [], "role": "GM"}}
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        merged = tmp_path / "merged.txt"
        merged.write_text("irrelevant\n", encoding="utf-8")

        out = format_context(tmp_path, merged, "irrelevant\n")

        assert "- 1-gm: GM [GM]" in out

    def test_legacy_shape_still_renders(self, tmp_path):
        """``character: "X"`` legacy shape must render same as new shape."""
        from core.chunking import format_context

        data = {
            "1-pc": {"player": "Alice", "character": "Aragorn", "role": "PC"},
        }
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        merged = tmp_path / "merged.txt"
        merged.write_text("irrelevant\n", encoding="utf-8")

        out = format_context(tmp_path, merged, "irrelevant\n")

        assert "- 1-pc: Alice / Aragorn [PC]" in out
