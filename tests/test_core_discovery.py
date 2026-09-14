"""Tier 1 — core.discovery helper tests.

Tests find_info_file with tmp_path fixtures.
No audio, no models. Must run in <5s.

Чат-лог ищет core.file_matchers.detect_fvtt_chat_logs — один искатель
на экран сессии и на мердж; его тесты в test_core_file_matchers.py и
в test_chat_log_finder_agreement.py.
"""

import pytest
from pathlib import Path


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
