"""Unit tests for :mod:`ui.shell.add_source_dialog`.

Covers the public surface of the parser picker:

    * :func:`build_parser_options` returns the expected keys and pairs
      speech parsers with the matching :class:`BackendId`.
    * ``AddSourceDialog`` exposes the user's selection via
      ``selected_key`` after accept, and returns ``None`` on reject.
    * Install-state hints reflect whether the backing bundle is on disk
      according to :func:`core.backend_installers.is_backend_installed`.

All Qt-dependent tests are marked ``gui`` and gated on ``pytestqt`` so
CI without a display (or without the ``gui`` marker enabled) still runs
the pure-Python tests. Heavy constructor work is avoided — we never
touch real model files or network.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


class TestBuildParserOptions:
    """`build_parser_options()` is pure Python, no Qt needed."""

    def test_keys_contain_all_parsers(self):
        from ui.shell.add_source_dialog import (
            KEY_FASTER_WHISPER,
            KEY_FVTT_CHAT,
            KEY_GIGAAM,
            build_parser_options,
        )

        keys = [o.key for o in build_parser_options()]
        assert KEY_GIGAAM in keys
        assert KEY_FASTER_WHISPER in keys
        assert KEY_FVTT_CHAT in keys

    def test_speech_options_have_backend_ids(self):
        from core.backend_installers import BackendId
        from ui.shell.add_source_dialog import (
            KEY_FASTER_WHISPER,
            KEY_GIGAAM,
            build_parser_options,
        )

        by_key = {o.key: o for o in build_parser_options()}
        assert by_key[KEY_GIGAAM].backend_id == BackendId.GIGAAM_RNNT_FP32
        assert (
            by_key[KEY_FASTER_WHISPER].backend_id
            == BackendId.FASTER_WHISPER_LARGE_V3_RU
        )

    def test_chat_option_has_no_backend(self):
        from ui.shell.add_source_dialog import (
            KEY_FVTT_CHAT,
            build_parser_options,
        )

        by_key = {o.key: o for o in build_parser_options()}
        assert by_key[KEY_FVTT_CHAT].backend_id is None

    def test_subtitles_mention_size_for_speech_parsers(self):
        from ui.shell.add_source_dialog import (
            KEY_FASTER_WHISPER,
            KEY_GIGAAM,
            build_parser_options,
        )

        by_key = {o.key: o for o in build_parser_options()}
        assert "MB" in by_key[KEY_GIGAAM].subtitle
        assert "MB" in by_key[KEY_FASTER_WHISPER].subtitle


# ── Qt-dependent behaviour ────────────────────────────────────────────


@pytest.mark.gui
class TestDialogSelection:
    def test_accept_with_current_row_sets_selected_key(self, qtbot, monkeypatch):
        # Keep the install-state probe cheap and deterministic so the
        # test doesn't touch real model directories.
        monkeypatch.setattr(
            "ui.shell.add_source_dialog.is_backend_installed",
            lambda _bid: False,
        )

        from ui.shell.add_source_dialog import AddSourceDialog

        dlg = AddSourceDialog()
        qtbot.addWidget(dlg)
        # First row is picked by default
        dlg._list.setCurrentRow(0)  # noqa: SLF001
        dlg._accept()  # noqa: SLF001 — bypass showing a real button
        assert dlg.selected_key is not None

    def test_reject_leaves_selected_key_none(self, qtbot, monkeypatch):
        monkeypatch.setattr(
            "ui.shell.add_source_dialog.is_backend_installed",
            lambda _bid: False,
        )

        from ui.shell.add_source_dialog import AddSourceDialog

        dlg = AddSourceDialog()
        qtbot.addWidget(dlg)
        dlg.reject()
        assert dlg.selected_key is None

    def test_list_reflects_installed_state(self, qtbot, monkeypatch):
        """Items tagged with the correct status label based on install state."""
        monkeypatch.setattr(
            "ui.shell.add_source_dialog.is_backend_installed",
            lambda _bid: True,  # pretend everything is installed
        )

        from ui.shell.add_source_dialog import AddSourceDialog

        dlg = AddSourceDialog()
        qtbot.addWidget(dlg)
        texts = [
            dlg._list.item(i).text()  # noqa: SLF001
            for i in range(dlg._list.count())  # noqa: SLF001
        ]
        assert any("установлен" in t for t in texts)

    def test_list_marks_missing_install_as_required(self, qtbot, monkeypatch):
        monkeypatch.setattr(
            "ui.shell.add_source_dialog.is_backend_installed",
            lambda _bid: False,
        )

        from ui.shell.add_source_dialog import AddSourceDialog

        dlg = AddSourceDialog()
        qtbot.addWidget(dlg)
        texts = [
            dlg._list.item(i).text()  # noqa: SLF001
            for i in range(dlg._list.count())  # noqa: SLF001
        ]
        # Speech parsers should advertise the pending install
        assert any("потребуется установка" in t for t in texts)
        # Chat parser stays ready even without any models
        assert any("готов" in t for t in texts)
