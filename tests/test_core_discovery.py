"""Tier 1 — core.discovery helper tests.

Tests find_fvtt_chat_log and find_info_file with tmp_path fixtures.
No audio, no models. Must run in <5s.
"""

import pytest
from pathlib import Path


class TestFindFvttChatLog:
    def test_returns_none_when_no_fvtt_files(self, tmp_path):
        from core.discovery import find_fvtt_chat_log
        result = find_fvtt_chat_log(tmp_path)
        assert result is None

    def test_returns_first_alphabetically(self, tmp_path):
        from core.discovery import find_fvtt_chat_log
        (tmp_path / "fvtt-log-20250711.txt").write_text("b", encoding="utf-8")
        (tmp_path / "fvtt-log-20250710.txt").write_text("a", encoding="utf-8")
        result = find_fvtt_chat_log(tmp_path)
        assert result is not None
        assert result.name == "fvtt-log-20250710.txt"

    def test_returns_single_file(self, tmp_path):
        from core.discovery import find_fvtt_chat_log
        p = tmp_path / "fvtt-log-session1.txt"
        p.write_text("log content", encoding="utf-8")
        result = find_fvtt_chat_log(tmp_path)
        assert result == p

    def test_ignores_non_fvtt_files(self, tmp_path):
        from core.discovery import find_fvtt_chat_log
        (tmp_path / "merged.txt").write_text("not fvtt", encoding="utf-8")
        (tmp_path / "speaker_map.json").write_text("{}", encoding="utf-8")
        result = find_fvtt_chat_log(tmp_path)
        assert result is None

    def test_returns_path_object(self, tmp_path):
        from core.discovery import find_fvtt_chat_log
        (tmp_path / "fvtt-log-x.txt").write_text("x", encoding="utf-8")
        result = find_fvtt_chat_log(tmp_path)
        assert isinstance(result, Path)


class TestFindInfoFile:
    def test_returns_none_when_no_info_txt(self, tmp_path):
        from core.discovery import find_info_file
        result = find_info_file(tmp_path)
        assert result is None

    def test_returns_path_when_info_txt_exists(self, tmp_path):
        from core.discovery import find_info_file
        info = tmp_path / "info.txt"
        info.write_text("Start time: 2025-07-11T15:00:00Z\n", encoding="utf-8")
        result = find_info_file(tmp_path)
        assert result == info

    def test_returns_path_object(self, tmp_path):
        from core.discovery import find_info_file
        (tmp_path / "info.txt").write_text("x", encoding="utf-8")
        result = find_info_file(tmp_path)
        assert isinstance(result, Path)

    def test_does_not_find_info_in_subdir(self, tmp_path):
        from core.discovery import find_info_file
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "info.txt").write_text("Start time: ...", encoding="utf-8")
        result = find_info_file(tmp_path)
        # info.txt is in sub/, not in tmp_path directly
        assert result is None
