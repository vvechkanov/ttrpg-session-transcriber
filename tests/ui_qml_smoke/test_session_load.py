"""Открытие сессии наполняет обе списочные модели — через ПРОДАКШН-проводку.

Файл был скриптом с ``main()``: pytest собирал из него ноль тестов.

Проводку здесь гоняет ``ui.app_qml.build_shell`` — тот самый вызов, что
собирает объектный граф для настоящего приложения, — а не пересобранные
в фикстуре ``connect``. Разница не стилистическая, и внешнее ревью
поймало её первым: тест, который сам соединяет ``sessionOpened`` с
загрузчиками, остаётся зелёным, даже если ``build_shell`` перестанет их
соединять. То есть он проверял бы ``SessionMeta`` и загрузчики моделей,
но не точку входа, которой служит, — ровно то, что запрещает
``AGENTS.md`` («Фича должна доходить до точки входа»). Докстринг самого
``build_shell`` требует того же: «every consumer … drives the same
wiring instead of re-deriving it».

Отдельного контрольного случая («без подключения сигнала модели пусты»)
здесь больше нет, и он не нужен: если ``build_shell`` потеряет любой из
двух ``connect``, соответствующая модель останется пустой и проверки
ниже покраснеют сами.

Замер: весь файл идёт 0.40 с, три прогона подряд одинаковы. Аудио в
фикстуре — настоящие крошечные WAV, а не нулевые байты, и это про
время: ``build_shell`` поднимает на открытие папки ``PeaksWorker``, и
на неразбираемых файлах извлечение пиков тянуло 11 секунд.
"""

from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Как и у соседей: core.pipeline импортируется до ui.*, чтобы не поймать
# циклический импорт через sources/__init__.
from core.pipeline import run as _warm  # noqa: F401,E402

from PySide6.QtCore import QSettings, QStandardPaths, QThread  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402

from ui.app_qml import build_shell  # noqa: E402
from ui.models import SourceListModel, TrackListModel  # noqa: E402


def _silent_wav_bytes(duration_sec: float = 0.05, sample_rate: int = 8_000) -> bytes:
    """Минимальный валидный моно-PCM WAV, без внешних зависимостей."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * int(duration_sec * sample_rate))
    return buf.getvalue()


@pytest.fixture(scope="module")
def opened_session(tmp_path_factory):
    """Настоящий shell, открывший папку сессии в стиле Craig.

    Область module: ``build_shell`` грузит ``Main.qml`` целиком, и делать
    это на каждую проверку незачем — ни одна из них ничего не меняет.
    """
    tmp_root = tmp_path_factory.mktemp("session-load")

    # QSettings уводится до build_shell: он строит AppPreferences и
    # ModelRegistry, которые читают хранилище в конструкторе. Обратно
    # путь не возвращается — прочитать исходный QSettings не даёт; см.
    # ту же оговорку в test_app_preferences.py.
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_root)
    )

    app = QGuiApplication.instance() or QGuiApplication(sys.argv or [""])
    QQuickStyle.setStyle("Basic")

    session = tmp_root / "Storm King" / "Session 14"
    session.mkdir(parents=True)
    # Подорожечные записи плюс сведённый микс, который обязан отсеяться.
    #
    # Файлы НАСТОЯЩИЕ, а не шестнадцать нулевых байт, и это про время:
    # build_shell поднимает PeaksWorker на каждое открытие папки, и на
    # неразбираемых файлах извлечение пиков тянулось 11 секунд, тогда
    # как на валидных укладывается в доли. Замерено.
    for name in ("Andrey.wav", "Boris.wav", "craig-mix.wav"):
        (session / name).write_bytes(_silent_wav_bytes())
    (session / "fvtt-log.txt").write_text("fake fvtt log", encoding="utf-8")
    (session / "combat-goblins.json").write_text("{}", encoding="utf-8")

    shell = build_shell(app)
    assert shell.engine.rootObjects(), "Main.qml не разобрался — сломана сама проба"

    shell.session_meta.openSession(str(session))
    try:
        yield shell
    finally:
        # Дождаться PeaksWorker. Без этого Qt печатает «QThread:
        # Destroyed while thread '' is still running» на выходе — то
        # самое teardown-сообщение, которого в наборе и так хватает;
        # заводить ещё одно, да ещё и своё, нельзя.
        thread = shell.peaks_state.get("thread")
        if isinstance(thread, QThread) and thread.isRunning():
            thread.quit()
            thread.wait(5000)
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.TempLocation
            ),
        )


def test_titles_come_from_the_path(opened_session):
    assert opened_session.session_meta.sessionTitle == "Session 14"
    assert opened_session.session_meta.campaignTitle == "Storm King"


def test_tracks_model_is_filled_and_mixdown_filtered(opened_session):
    """Микс-даун Craig — не дорожка игрока, и в список он попасть не должен.

    Пустая модель здесь означает, что ``build_shell`` перестал соединять
    ``sessionOpened`` с ``TrackListModel.loadFromDir``; про это сказано в
    сообщении, чтобы читатель не искал дефект в отборе файлов.
    """
    tracks = opened_session.tracks_model

    assert tracks.rowCount() == 2, (
        f"дорожек {tracks.rowCount()}, ожидалось 2 — либо микс-даун не "
        "отсеян, либо build_shell больше не соединяет sessionOpened с "
        "TrackListModel.loadFromDir"
    )
    names = {
        tracks.data(tracks.index(i, 0), TrackListModel.NameRole)
        for i in range(tracks.rowCount())
    }
    assert names == {"Andrey", "Boris"}


def test_sources_model_is_filled_with_both_parsers(opened_session):
    sources = opened_session.sources_model

    assert sources.rowCount() == 2, (
        f"источников {sources.rowCount()}, ожидалось 2 — возможно, "
        "build_shell больше не соединяет sessionOpened с "
        "SourceListModel.loadFromDir"
    )
    parser_ids = {
        sources.data(sources.index(i, 0), SourceListModel.ParserIdRole)
        for i in range(sources.rowCount())
    }
    assert parser_ids == {"foundry-chat", "combat-log"}
