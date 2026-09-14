"""Один искатель чат-лога — общий для экрана сессии и для мерджа.

Карточка https://trello.com/c/eyFOj25c . В проекте жили две функции
поиска фаундривского чат-лога с разными шаблонами имени:

* ``core.discovery.find_fvtt_chat_log`` — ``glob("fvtt-log-*.txt")``,
  дефис обязателен, регистр значим; ею пользовался пайплайн;
* ``core.file_matchers.detect_fvtt_chat_logs`` — ``fvtt-log*.txt``
  без учёта регистра; ею пользуется экран сессии.

Последствие — файл виден в интерфейсе как найденный источник и молча
не доезжает до ``merged.txt``. Тест держит инвариант: **что показано,
то и открывается**.

Расхождение шире, чем «нужен ли дефис», поэтому корпус имён покрывает
все четыре оси, на которых два шаблона расходились: отсутствие дефиса,
произвольный символ вместо него, регистр расширения, регистр имени.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.file_matchers import detect_fvtt_chat_logs
from core.pipeline import PipelineParams, run
from sources.base import Source

#: Имена, которые экран сессии показывает как «Foundry чат», а прежний
#: узкий шаблон пайплайна не находил. Каждое — отдельная ось расхождения.
NAMES_ONLY_THE_UI_SAW = [
    "fvtt-log.txt",
    "fvtt-log2.txt",
    "fvtt-log.TXT",
    "FVTT-LOG-2026.txt",
]

#: Каноническое имя, которое находили обе функции. Держится в том же
#: наборе, чтобы правка не закрыла расхождение ценой прежнего случая.
CANONICAL_NAME = "fvtt-log-2025-07-11.txt"


class _FakeSource(Source):
    name = "fake"

    def __init__(self, **_: Any) -> None:
        pass

    def extract(self, session_dir: Path) -> list:
        return []


class _FakeMerger:
    def merge(self, timeline):
        return []


class _FakeRenderer:
    def render(self, events) -> bytes:
        return b""


class _FakeChatSource:
    """Разбор чата тут не проверяется — только то, какой файл открыт.

    Путь запоминается, потому что сообщение стадии ``chat`` — это то,
    что пайплайн **объявил**, а не то, что он открыл. Мутация, в
    которой объявлен один файл, а в источник передан другой, проходила
    мимо теста, пока он смотрел только на сообщение.
    """

    #: Путь последнего построенного источника, или ``None``.
    opened: Path | None = None

    def __init__(self, **kwargs: Any) -> None:
        _FakeChatSource.opened = kwargs.get("chat_log_path")

    def extract(self, session_dir: Path) -> list:
        return []


@pytest.fixture
def patched_pipeline(monkeypatch: pytest.MonkeyPatch):
    """Пайплайн без ASR, GPU и разбора чата — остаётся только поиск."""
    monkeypatch.setattr("core.pipeline.SPEECH_SOURCES", {"fake": _FakeSource})
    monkeypatch.setattr("core.pipeline.MERGERS", {"script": _FakeMerger})
    monkeypatch.setattr(
        "core.pipeline.get_renderer", lambda name: _FakeRenderer()
    )
    monkeypatch.setattr("core.pipeline.check_gpu_or_warn", lambda device: None)
    monkeypatch.setattr("core.pipeline._speech_kwargs", lambda p, c: {})
    monkeypatch.setattr("core.pipeline.FvttChatSource", _FakeChatSource)


def _params() -> PipelineParams:
    return PipelineParams(
        speech_backend="fake",
        merger="script",
        renderer="plain-text",
        output_filename="merged.txt",
        device="cpu",
    )


def _chat_stage_message(session_dir: Path) -> str:
    """Сообщение стадии ``chat`` — имя объявленного файла или «no chat log»."""
    seen: list[tuple[str, str]] = []
    _FakeChatSource.opened = None
    run(session_dir, _params(), on_stage=lambda s, m: seen.append((s, m)))
    return next(msg for stage, msg in seen if stage == "chat")


def _session_with(tmp_path: Path, *names: str) -> Path:
    session = tmp_path / "session"
    session.mkdir()
    for name in names:
        (session / name).write_text("chat\n", encoding="utf-8")
    return session


class TestTheUiAndThePipelineAgree:
    @pytest.mark.parametrize(
        "name", [*NAMES_ONLY_THE_UI_SAW, CANONICAL_NAME]
    )
    def test_pipeline_opens_every_log_the_ui_lists(
        self, tmp_path: Path, name: str, patched_pipeline
    ):
        """Показано на экране → открыто мерджем. Ровно этот инвариант."""
        session = _session_with(tmp_path, name)

        listed = [p.name for p in detect_fvtt_chat_logs(session)]
        assert listed == [name], "экран сессии не показал файл — тест не о том"

        assert _chat_stage_message(session) == name
        # Объявить и открыть — разные вещи; проверяем вторую.
        assert _FakeChatSource.opened is not None
        assert _FakeChatSource.opened.name == name

    def test_the_two_finders_return_the_same_set(
        self, tmp_path: Path, patched_pipeline
    ):
        """Весь корпус разом: множества совпадают, а не пересекаются."""
        session = _session_with(
            tmp_path, *NAMES_ONLY_THE_UI_SAW, CANONICAL_NAME
        )

        found = detect_fvtt_chat_logs(session)
        assert {p.name for p in found} == {
            *NAMES_ONLY_THE_UI_SAW,
            CANONICAL_NAME,
        }

        # Не «из того же набора», а именно тот же элемент: пайплайн
        # берёт первый, и первым обязан быть тот же файл, который
        # экран сессии показывает первым. Слабее — и тест зеленеет,
        # пока стороны расходятся на регистре имени.
        assert _chat_stage_message(session) == found[0].name

    def test_a_name_neither_side_claims_is_still_ignored(
        self, tmp_path: Path, patched_pipeline
    ):
        """Расширение шаблона не должно втянуть посторонние файлы."""
        session = _session_with(tmp_path, "fvtt_log.txt", "chat.txt")

        assert detect_fvtt_chat_logs(session) == ()
        assert _chat_stage_message(session) == "no chat log"


class TestOnlyOneFinderRemains:
    def test_discovery_no_longer_ships_a_second_chat_finder(self):
        """«Свести к одной функции» — машинная форма этого требования.

        Пока две функции существуют рядом, они снова разойдутся: именно
        так и вышло в прошлый раз. Держим отсутствие второй, а не
        совпадение двух шаблонов.
        """
        import core.discovery

        assert not hasattr(core.discovery, "find_fvtt_chat_log")
