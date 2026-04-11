"""Tests for ``core.speaker_map`` raw helpers and legacy migration.

These cover the GUI-facing side of the speaker map module (raw nested dict
I/O + one-shot migration of legacy ``<project_root>/speaker_map.json`` into
the session folder). The rendered/flat shape used by the ASR pipeline is
covered separately in ``tests/test_domain.py``.
"""

import json
from unittest.mock import patch


class TestLoadSpeakerMapRaw:
    def test_reads_nested_dict_from_session_dir(self, tmp_path):
        from core.speaker_map import load_speaker_map_raw

        data = {
            "1-gm": {"player": "Alice", "character": "", "role": "GM"},
            "2-pc": {"player": "Bob", "character": "Aragorn", "role": "PC"},
        }
        (tmp_path / "speaker_map.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

        result = load_speaker_map_raw(tmp_path)

        # Raw loader must preserve the nested structure (not render labels).
        assert result == data
        assert result["2-pc"]["character"] == "Aragorn"

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
            "1-gm": {"player": "Ведущий", "character": "", "role": "GM"},
            "2-pc": {"player": "Алиса", "character": "Арагорн", "role": "PC"},
        }

        path = save_speaker_map_raw(tmp_path, data)

        assert path == tmp_path / "speaker_map.json"
        assert path.exists()
        # ensure_ascii=False → Cyrillic must be preserved as-is on disk.
        raw = path.read_text(encoding="utf-8")
        assert "Ведущий" in raw
        assert "Арагорн" in raw
        # Round-trip via load must match.
        assert load_speaker_map_raw(tmp_path) == data

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
