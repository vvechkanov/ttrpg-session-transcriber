"""``SessionMeta.openSession`` наполняет обе списочные модели.

Файл был скриптом с ``main()``: pytest собирал из него ноль тестов.
Проверяется здесь именно ПРОВОДКА — сигнал ``sessionOpened`` доходит до
``TrackListModel.loadFromDir`` и ``SourceListModel.loadFromDir``, — а её
не проверяет ни ``tests/test_core_file_matchers.py`` (чистый core), ни
``tests/test_ui_models_session.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from PySide6.QtGui import QGuiApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ui.models import SessionMeta, SourceListModel, TrackListModel  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    created = QGuiApplication(sys.argv or [""])
    created.setApplicationName("session-load-test")
    created.setOrganizationName("session-load-test")
    return created


@pytest.fixture()
def opened_session(app: QGuiApplication, tmp_path: Path):
    """Папка сессии в стиле Craig, открытая через ``openSession``."""
    campaign = tmp_path / "Storm King"
    session = campaign / "Session 14"
    session.mkdir(parents=True)

    # Подорожечные flac плюс сведённый микс, который обязан отсеяться.
    (session / "Andrey.flac").write_bytes(b"\x00" * 16)
    (session / "Boris.flac").write_bytes(b"\x00" * 16)
    (session / "craig-mix.flac").write_bytes(b"\x00" * 16)
    (session / "fvtt-log.txt").write_text("fake fvtt log", encoding="utf-8")
    (session / "combat-goblins.json").write_text("{}", encoding="utf-8")

    meta = SessionMeta()
    tracks = TrackListModel()
    sources = SourceListModel()
    meta.sessionOpened.connect(tracks.loadFromDir)
    meta.sessionOpened.connect(sources.loadFromDir)

    meta.openSession(str(session))
    return meta, tracks, sources


def test_titles_come_from_the_path(opened_session):
    meta, _tracks, _sources = opened_session
    assert meta.sessionTitle == "Session 14"
    assert meta.campaignTitle == "Storm King"


def test_tracks_model_is_filled_and_mixdown_filtered(opened_session):
    """Микс-даун Craig — не дорожка игрока, и в список он попасть не должен."""
    _meta, tracks, _sources = opened_session

    assert tracks.rowCount() == 2, (
        f"дорожек {tracks.rowCount()}, ожидалось 2 — микс-даун не отсеян "
        "или сигнал не дошёл до модели"
    )
    names = {
        tracks.data(tracks.index(i, 0), TrackListModel.NameRole)
        for i in range(tracks.rowCount())
    }
    assert names == {"Andrey", "Boris"}


def test_sources_model_is_filled_with_both_parsers(opened_session):
    _meta, _tracks, sources = opened_session

    assert sources.rowCount() == 2, (
        f"источников {sources.rowCount()}, ожидалось 2 — сигнал не дошёл "
        "до модели источников"
    )
    parser_ids = {
        sources.data(sources.index(i, 0), SourceListModel.ParserIdRole)
        for i in range(sources.rowCount())
    }
    assert parser_ids == {"foundry-chat", "combat-log"}


def test_models_stay_empty_without_the_signal(app: QGuiApplication, tmp_path: Path):
    """Контрольный случай: без подключения сигнала модели пусты.

    Без него три теста выше зеленели бы и на модели, которая наполняется
    сама по себе, и проводку они бы не проверяли вовсе.
    """
    session = tmp_path / "Camp" / "Session 1"
    session.mkdir(parents=True)
    (session / "Andrey.flac").write_bytes(b"\x00" * 16)
    (session / "fvtt-log.txt").write_text("fake fvtt log", encoding="utf-8")

    meta = SessionMeta()
    tracks = TrackListModel()
    sources = SourceListModel()
    # Сигнал намеренно НЕ подключён.
    meta.openSession(str(session))

    assert tracks.rowCount() == 0
    assert sources.rowCount() == 0
