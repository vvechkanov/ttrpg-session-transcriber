"""Integration test: ``SessionMeta.openSession`` feeds TrackList/SourceList.

Creates a temp session dir with fake audio + chat + combat files,
invokes ``openSession``, and asserts the list models now hold rows
sourced from ``core.file_matchers``.

Run as::

    QT_QPA_PLATFORM=offscreen python tests/ui_qml_smoke/test_session_load.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtGui import QGuiApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ui.models import SessionMeta, SourceListModel, TrackListModel  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        sys.stderr.write(f"FAIL: {msg}\n")
        raise SystemExit(1)


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("smoke")
    app.setOrganizationName("smoke")

    with tempfile.TemporaryDirectory() as tmp_root:
        campaign = Path(tmp_root) / "Storm King"
        campaign.mkdir()
        session = campaign / "Session 14"
        session.mkdir()

        # Craig-style per-speaker flacs + a mix-down that must be skipped.
        (session / "Andrey.flac").write_bytes(b"\x00" * 16)
        (session / "Boris.flac").write_bytes(b"\x00" * 16)
        (session / "craig-mix.flac").write_bytes(b"\x00" * 16)  # must be filtered
        # Chat + combat logs.
        (session / "fvtt-log.txt").write_text("fake fvtt log", encoding="utf-8")
        (session / "combat-goblins.json").write_text("{}", encoding="utf-8")

        meta = SessionMeta()
        tracks = TrackListModel()
        sources = SourceListModel()
        meta.sessionOpened.connect(tracks.loadFromDir)
        meta.sessionOpened.connect(sources.loadFromDir)

        meta.openSession(str(session))

        _assert(meta.sessionTitle == "Session 14", f"session title: {meta.sessionTitle!r}")
        _assert(meta.campaignTitle == "Storm King", f"campaign: {meta.campaignTitle!r}")

        # 2 per-speaker tracks (craig mix filtered out).
        _assert(tracks.rowCount() == 2, f"tracks: {tracks.rowCount()}")
        names = {tracks.data(tracks.index(i, 0), TrackListModel.NameRole) for i in range(2)}
        _assert(names == {"Andrey", "Boris"}, f"names: {names}")

        # 2 sources (1 fvtt log + 1 combat log).
        _assert(sources.rowCount() == 2, f"sources: {sources.rowCount()}")
        parser_ids = [
            sources.data(sources.index(i, 0), SourceListModel.ParserIdRole)
            for i in range(2)
        ]
        _assert(
            "foundry-chat" in parser_ids and "combat-log" in parser_ids,
            f"parsers: {parser_ids}",
        )

    print("OK: SessionMeta.openSession populates both list models via core.file_matchers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
