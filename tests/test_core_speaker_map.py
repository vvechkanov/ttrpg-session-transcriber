"""Tests for ``core.speaker_map`` raw helpers and legacy migration.

These cover the GUI-facing side of the speaker map module (raw nested dict
I/O + one-shot migration of legacy ``<project_root>/speaker_map.json`` into
the session folder). The rendered/flat shape used by the ASR pipeline is
covered separately in ``tests/test_domain.py``.
"""

import json
from unittest.mock import patch

import pytest


class TestNormalizeEntry:
    """Direct unit tests for the private ``_normalize_entry`` helper.

    Covers malformed / edge-case inputs that the loader must tolerate without
    raising, so the GUI can open any plausibly-shaped ``speaker_map.json``.

    Policy decisions codified here (see implementation docstring):

    - Non-string ``player`` / ``role`` (None, 42) coerce to ``""``.
    - Non-string element inside ``characters`` list is **dropped** (not
      coerced via ``str()``) — avoids accidental ``"42"`` UI labels.
    - Malformed scalar ``characters: "Aragorn"`` is **wrapped** into
      ``["Aragorn"]`` — robust over strict.
    - Whitespace-only character entries are stripped and dropped.
    - Unknown keys pass through verbatim, except legacy ``character``
      which is collapsed into ``characters``.
    """

    @pytest.mark.parametrize(
        "raw",
        [None, [], "string", 42, 3.14],
        ids=["none", "list", "string", "int", "float"],
    )
    def test_non_dict_input_returns_empty_canonical(self, raw):
        from core.speaker_map import _normalize_entry

        assert _normalize_entry(raw) == {
            "player": "",
            "characters": [],
            "role": "",
        }

    def test_empty_dict_returns_empty_canonical(self):
        from core.speaker_map import _normalize_entry

        assert _normalize_entry({}) == {
            "player": "",
            "characters": [],
            "role": "",
        }

    def test_legacy_character_collapses_to_characters_list(self):
        from core.speaker_map import _normalize_entry

        result = _normalize_entry(
            {"player": "X", "character": "Y", "role": "PC"}
        )

        assert result == {"player": "X", "characters": ["Y"], "role": "PC"}
        assert "character" not in result

    def test_new_shape_multi_character_passes_through(self):
        from core.speaker_map import _normalize_entry

        result = _normalize_entry(
            {"player": "X", "characters": ["A", "B"], "role": "PC"}
        )

        assert result == {
            "player": "X",
            "characters": ["A", "B"],
            "role": "PC",
        }

    def test_legacy_empty_string_character_becomes_empty_list(self):
        from core.speaker_map import _normalize_entry

        result = _normalize_entry({"character": ""})

        assert result["characters"] == []

    def test_malformed_scalar_characters_is_wrapped_into_list(self):
        """``characters: "Aragorn"`` (string instead of list) → ``["Aragorn"]``."""
        from core.speaker_map import _normalize_entry

        result = _normalize_entry({"player": "X", "characters": "Aragorn"})

        assert result["characters"] == ["Aragorn"]

    def test_malformed_empty_scalar_characters_becomes_empty_list(self):
        from core.speaker_map import _normalize_entry

        result = _normalize_entry({"player": "X", "characters": "   "})

        assert result["characters"] == []

    def test_characters_list_strips_whitespace_and_drops_empty(self):
        from core.speaker_map import _normalize_entry

        result = _normalize_entry(
            {"characters": [None, "", "  ", "Valid"]}
        )

        assert result["characters"] == ["Valid"]

    def test_characters_list_drops_non_string_elements(self):
        """Non-string in list is **dropped** (not coerced via str())."""
        from core.speaker_map import _normalize_entry

        result = _normalize_entry({"characters": [42, "Valid", 3.14, True]})

        assert result["characters"] == ["Valid"]

    def test_extras_preserved_verbatim(self):
        from core.speaker_map import _normalize_entry

        result = _normalize_entry(
            {
                "player": "X",
                "characters": ["Y"],
                "note": "MVP plays two PCs",
                "color": "#ff0",
            }
        )

        assert result["player"] == "X"
        assert result["characters"] == ["Y"]
        assert result["note"] == "MVP plays two PCs"
        assert result["color"] == "#ff0"

    def test_non_string_player_and_role_coerce_to_empty_string(self):
        from core.speaker_map import _normalize_entry

        result = _normalize_entry({"player": None, "role": 42})

        assert result["player"] == ""
        assert result["role"] == ""

    def test_mixed_malformed_input(self):
        """Nested extras preserved; None player/role → ''; non-string in list dropped."""
        from core.speaker_map import _normalize_entry

        result = _normalize_entry(
            {
                "player": None,
                "characters": [42, "Aragorn"],
                "role": None,
                "extra": {"nested": True},
            }
        )

        assert result == {
            "player": "",
            "characters": ["Aragorn"],
            "role": "",
            "extra": {"nested": True},
        }

    def test_legacy_character_key_not_preserved_as_extra(self):
        """Legacy ``character`` key must be collapsed, not leak as extra."""
        from core.speaker_map import _normalize_entry

        result = _normalize_entry(
            {"player": "X", "character": "Y", "role": "PC", "note": "keep"}
        )

        assert "character" not in result
        assert result["characters"] == ["Y"]
        assert result["note"] == "keep"


class TestLoadSpeakerMapRaw:
    def test_reads_new_shape_roundtrip(self, tmp_path):
        """File already in new shape round-trips through load unchanged."""
        from core.speaker_map import load_speaker_map_raw

        data = {
            "1-gm": {"player": "Alice", "characters": [], "role": "GM"},
            "2-pc": {
                "player": "Bob",
                "characters": ["Aragorn", "Strider"],
                "role": "PC",
            },
        }
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = load_speaker_map_raw(tmp_path)

        assert result == data
        assert result["2-pc"]["characters"] == ["Aragorn", "Strider"]

    def test_legacy_shape_normalized_on_load_file_unchanged(self, tmp_path):
        """Old-shape file surfaces as new shape; disk file stays untouched."""
        from core.speaker_map import load_speaker_map_raw

        legacy_data = {
            "1-pc": {"player": "Bob", "character": "Aragorn", "role": "PC"},
        }
        path = tmp_path / "speaker_map.json"
        path.write_text(json.dumps(legacy_data), encoding="utf-8")
        original_bytes = path.read_bytes()

        result = load_speaker_map_raw(tmp_path)

        assert result == {
            "1-pc": {"player": "Bob", "characters": ["Aragorn"], "role": "PC"},
        }
        # File on disk must NOT be rewritten by the reader.
        assert path.read_bytes() == original_bytes

    def test_mixed_shape_normalized_per_entry(self, tmp_path):
        """Mixed file with some legacy + some new entries normalizes per entry."""
        from core.speaker_map import load_speaker_map_raw

        data = {
            "1-gm": {"player": "GM", "character": "", "role": "GM"},
            "2-new": {"player": "Alice", "characters": ["Odette"], "role": "PC"},
            "3-legacy": {"player": "Bob", "character": "Aragorn", "role": "PC"},
        }
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = load_speaker_map_raw(tmp_path)

        assert result["1-gm"] == {"player": "GM", "characters": [], "role": "GM"}
        assert result["2-new"] == {
            "player": "Alice",
            "characters": ["Odette"],
            "role": "PC",
        }
        assert result["3-legacy"] == {
            "player": "Bob",
            "characters": ["Aragorn"],
            "role": "PC",
        }

    def test_gm_entry_without_character_key_becomes_empty_list(self, tmp_path):
        """GM entry with missing ``character`` key normalizes to empty list."""
        from core.speaker_map import load_speaker_map_raw

        data = {"1-gm": {"player": "GM", "role": "GM"}}
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = load_speaker_map_raw(tmp_path)

        assert result["1-gm"]["characters"] == []

    def test_gm_entry_with_empty_string_character_becomes_empty_list(self, tmp_path):
        """``character: ""`` must become ``characters: []``, not ``[""]``."""
        from core.speaker_map import load_speaker_map_raw

        data = {"1-gm": {"player": "GM", "character": "", "role": "GM"}}
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = load_speaker_map_raw(tmp_path)

        assert result["1-gm"]["characters"] == []

    def test_returns_empty_on_missing_file(self, tmp_path):
        from core.speaker_map import load_speaker_map_raw

        empty_dir = tmp_path / "no_map_here"
        empty_dir.mkdir()
        # Patch project root fallback to somewhere empty too, so the repo's
        # own speaker_map.json doesn't leak into the test.
        fake_root = tmp_path / "fake_root"
        fake_root.mkdir()
        with patch("core.speaker_map._project_root", return_value=fake_root):
            result = load_speaker_map_raw(empty_dir)

        assert result == {}

    def test_returns_empty_on_invalid_json(self, tmp_path):
        from core.speaker_map import load_speaker_map_raw

        (tmp_path / "speaker_map.json").write_text("NOT JSON", encoding="utf-8")
        fake_root = tmp_path / "fake_root"
        fake_root.mkdir()
        with patch("core.speaker_map._project_root", return_value=fake_root):
            result = load_speaker_map_raw(tmp_path)

        assert result == {}

    def test_returns_empty_on_non_dict_top_level(self, tmp_path):
        from core.speaker_map import load_speaker_map_raw

        (tmp_path / "speaker_map.json").write_text("[]", encoding="utf-8")
        fake_root = tmp_path / "fake_root"
        fake_root.mkdir()
        with patch("core.speaker_map._project_root", return_value=fake_root):
            result = load_speaker_map_raw(tmp_path)

        assert result == {}


class TestSaveSpeakerMapRaw:
    def test_writes_utf8_to_session_dir(self, tmp_path):
        from core.speaker_map import load_speaker_map_raw, save_speaker_map_raw

        data = {
            "1-gm": {"player": "Ведущий", "characters": [], "role": "GM"},
            "2-pc": {
                "player": "Алиса",
                "characters": ["Арагорн"],
                "role": "PC",
            },
        }

        path = save_speaker_map_raw(tmp_path, data)

        assert path == tmp_path / "speaker_map.json"
        assert path.exists()
        # ensure_ascii=False → Cyrillic must be preserved as-is on disk.
        raw = path.read_text(encoding="utf-8")
        assert "Ведущий" in raw
        assert "Арагорн" in raw
        # Round-trip via load must match (new shape).
        assert load_speaker_map_raw(tmp_path) == data

    def test_save_normalizes_legacy_input_to_new_shape(self, tmp_path):
        """Defensive: if caller hands an old-shape dict, save normalizes it."""
        from core.speaker_map import save_speaker_map_raw

        legacy_input = {
            "1-pc": {"player": "Bob", "character": "Aragorn", "role": "PC"},
        }

        path = save_speaker_map_raw(tmp_path, legacy_input)

        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk == {
            "1-pc": {"player": "Bob", "characters": ["Aragorn"], "role": "PC"},
        }
        # Old key must not leak into the file.
        assert "character" not in on_disk["1-pc"]

    def test_save_preserves_multi_character_list(self, tmp_path):
        """Multi-character entries must round-trip exactly."""
        from core.speaker_map import load_speaker_map_raw, save_speaker_map_raw

        data = {
            "1-pc": {
                "player": "Alice",
                "characters": ["Одетт", "Lyra"],
                "role": "PC",
            },
        }

        save_speaker_map_raw(tmp_path, data)

        assert load_speaker_map_raw(tmp_path) == data

    def test_extras_roundtrip_through_save_and_load(self, tmp_path):
        """Unknown keys must survive the save → load round-trip verbatim."""
        from core.speaker_map import load_speaker_map_raw, save_speaker_map_raw

        data = {
            "1-pc": {
                "player": "Alice",
                "characters": ["Aragorn"],
                "role": "PC",
                "note": "двуручный меч",
                "color": "#ff0",
                "tags": ["fighter", "tank"],
            },
        }

        save_speaker_map_raw(tmp_path, data)
        reloaded = load_speaker_map_raw(tmp_path)

        assert reloaded == data
        assert reloaded["1-pc"]["note"] == "двуручный меч"
        assert reloaded["1-pc"]["color"] == "#ff0"
        assert reloaded["1-pc"]["tags"] == ["fighter", "tank"]

    def test_never_writes_to_project_root(self, tmp_path):
        from core.speaker_map import save_speaker_map_raw

        fake_root = tmp_path / "fake_root"
        fake_root.mkdir()
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        with patch("core.speaker_map._project_root", return_value=fake_root):
            save_speaker_map_raw(session_dir, {"1-gm": {"player": "X"}})

        assert (session_dir / "speaker_map.json").exists()
        assert not (fake_root / "speaker_map.json").exists()


class TestMigrateLegacySpeakerMap:
    def test_copies_legacy_file_when_session_has_none(self, tmp_path):
        from core.speaker_map import migrate_legacy_speaker_map

        fake_root = tmp_path / "fake_root"
        fake_root.mkdir()
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        legacy_data = {"1-gm": {"player": "LegacyGM", "character": "", "role": "GM"}}
        legacy_path = fake_root / "speaker_map.json"
        legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

        with patch("core.speaker_map._project_root", return_value=fake_root):
            result = migrate_legacy_speaker_map(session_dir)

        session_path = session_dir / "speaker_map.json"
        assert result == session_path
        assert session_path.exists()
        # Legacy file must remain intact — migration is non-destructive.
        assert legacy_path.exists()
        # Copied content matches byte-for-byte (same JSON).
        assert json.loads(session_path.read_text(encoding="utf-8")) == legacy_data

    def test_reload_after_migrate_surfaces_normalized_shape(self, tmp_path):
        """After legacy migration, re-loading must yield the new canonical shape."""
        from core.speaker_map import (
            load_speaker_map_raw,
            migrate_legacy_speaker_map,
        )

        fake_root = tmp_path / "fake_root"
        fake_root.mkdir()
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        legacy_data = {
            "1-gm": {"player": "GM", "character": "", "role": "GM"},
            "2-pc": {"player": "Bob", "character": "Aragorn", "role": "PC"},
        }
        legacy_path = fake_root / "speaker_map.json"
        legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

        with patch("core.speaker_map._project_root", return_value=fake_root):
            migrate_legacy_speaker_map(session_dir)
            result = load_speaker_map_raw(session_dir)

        assert result == {
            "1-gm": {"player": "GM", "characters": [], "role": "GM"},
            "2-pc": {"player": "Bob", "characters": ["Aragorn"], "role": "PC"},
        }

    def test_no_op_when_session_file_already_exists(self, tmp_path):
        from core.speaker_map import migrate_legacy_speaker_map

        fake_root = tmp_path / "fake_root"
        fake_root.mkdir()
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        session_path = session_dir / "speaker_map.json"
        session_content = {"existing": {"player": "Keep"}}
        session_path.write_text(json.dumps(session_content), encoding="utf-8")

        legacy_path = fake_root / "speaker_map.json"
        legacy_path.write_text(
            json.dumps({"legacy": {"player": "Ignore"}}), encoding="utf-8"
        )

        with patch("core.speaker_map._project_root", return_value=fake_root):
            result = migrate_legacy_speaker_map(session_dir)

        assert result is None
        # Session file must be untouched, not overwritten by legacy.
        assert json.loads(session_path.read_text(encoding="utf-8")) == session_content

    def test_no_op_when_neither_file_exists(self, tmp_path):
        from core.speaker_map import migrate_legacy_speaker_map

        fake_root = tmp_path / "fake_root"
        fake_root.mkdir()
        session_dir = tmp_path / "session"
        session_dir.mkdir()

        with patch("core.speaker_map._project_root", return_value=fake_root):
            result = migrate_legacy_speaker_map(session_dir)

        assert result is None
        assert not (session_dir / "speaker_map.json").exists()


class TestShimReExport:
    def test_rendered_load_still_available_via_core(self, tmp_path):
        """The legacy shim entry point must keep working for CLI."""
        from core.speaker_map import load_speaker_map

        data = {"1-pc": {"player": "Bob", "character": "Aragorn"}}
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = load_speaker_map(tmp_path)

        # Rendered shape: label, not nested dict.
        assert result["1-pc"] == "Bob (Aragorn)"
