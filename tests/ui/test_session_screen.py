"""Тесты ``ui.shell.screens.session_screen.SessionScreen`` (Phase 3).

Покрытие:
    * экран рендерится без исключений для idle-фикстуры;
    * breadcrumb отображает имена проекта и сессии из ``SessionScreenData``;
    * блок 1 создаёт ровно N ``SourceCard`` для N-элементной ``sources``
      + ровно один ``AddSourcePlaceholder``;
    * клик по ``[Настроить]`` на N-й карточке эмитит
      ``source_configure_requested(N)`` с корректным индексом;
    * клик ``+ добавить источник`` эмитит ``add_source_requested``;
    * клик ``[▶ Запустить обработку]`` эмитит ``run_clicked``;
    * клик ``[Настроить]`` на блоках мержер/вывод эмитит соответствующие
      сигналы.

Все тесты помечены ``gui``. В CI до Phase 9 GUI-тесты выключены.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QPushButton

from ui.shell.screens.session_screen import SessionScreen, SessionScreenData
from ui.widgets import AddSourcePlaceholder, SourceCard, SourceCardData


def _fixture_data(n_sources: int = 2) -> SessionScreenData:
    sources = tuple(
        SourceCardData(
            title=f"Источник {i}",
            subtitle=f"backend-{i}",
            files=(f"file-{i}.flac",),
            status="ready",
            status_text="готов",
        )
        for i in range(n_sources)
    )
    return SessionScreenData(
        project_name="Тест-проект",
        session_name="Тест-сессия",
        sources=sources,
    )


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.gui
class TestSmoke:
    def test_screen_builds_without_exception(self, qtbot):
        screen = SessionScreen(_fixture_data(), parent=None)
        qtbot.addWidget(screen)
        screen.show()
        qtbot.waitExposed(screen)
        assert screen.isVisible()

    def test_screen_builds_with_empty_sources(self, qtbot):
        """Сессия без источников всё равно должна показывать хотя бы
        placeholder + остальные блоки."""
        data = SessionScreenData(
            project_name="Empty",
            session_name="No sources yet",
            sources=(),
        )
        screen = SessionScreen(data)
        qtbot.addWidget(screen)
        screen.show()
        qtbot.waitExposed(screen)

        placeholders = screen.findChildren(AddSourcePlaceholder)
        assert len(placeholders) == 1


@pytest.mark.gui
class TestBreadcrumb:
    def test_breadcrumb_shows_project_and_session_names(self, qtbot):
        data = SessionScreenData(
            project_name="Dragonlance",
            session_name="Сессия 7 — Хан на холме",
        )
        screen = SessionScreen(data)
        qtbot.addWidget(screen)

        labels = [lbl.text() for lbl in screen.findChildren(QLabel)]
        assert "Dragonlance" in labels
        assert "Сессия 7 — Хан на холме" in labels


@pytest.mark.gui
class TestSourcesBlock:
    def test_source_card_count_matches_data(self, qtbot):
        data = _fixture_data(n_sources=3)
        screen = SessionScreen(data)
        qtbot.addWidget(screen)

        cards = screen.findChildren(SourceCard)
        assert len(cards) == 3

        placeholders = screen.findChildren(AddSourcePlaceholder)
        assert len(placeholders) == 1

    def test_configure_click_emits_correct_index(self, qtbot):
        data = _fixture_data(n_sources=3)
        screen = SessionScreen(data)
        qtbot.addWidget(screen)

        cards = screen.findChildren(SourceCard)
        received: list[int] = []
        screen.source_configure_requested.connect(received.append)

        # Эмитим напрямую с карточки — надёжнее оффскрин-клика
        cards[0].configure_clicked.emit()
        cards[2].configure_clicked.emit()

        assert received == [0, 2]


@pytest.mark.gui
class TestActionButtons:
    def test_run_button_emits_run_clicked(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)

        run_buttons = [
            b for b in screen.findChildren(QPushButton)
            if "Запустить" in b.text()
        ]
        assert len(run_buttons) == 1
        run_button = run_buttons[0]

        with qtbot.waitSignal(screen.run_clicked, timeout=1000):
            run_button.click()

    def test_add_source_button_emits(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)

        add_buttons = [
            b for b in screen.findChildren(QPushButton)
            if "добавить источник" in b.text()
        ]
        assert len(add_buttons) == 1

        with qtbot.waitSignal(screen.add_source_requested, timeout=1000):
            add_buttons[0].click()

    def test_placeholder_click_also_emits_add_source(self, qtbot):
        """Клик по dashed-плейсхолдеру эквивалентен кнопке в шапке."""
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)

        placeholders = screen.findChildren(AddSourcePlaceholder)
        assert len(placeholders) == 1

        received: list[None] = []
        screen.add_source_requested.connect(lambda: received.append(None))
        placeholders[0].clicked.emit()

        assert len(received) == 1

    def test_merger_configure_button_emits(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)

        # В блоке 2 / 4 / на карточках — кнопки с текстом "Настроить".
        # Блок 2 — первая из них, отфильтруем через parent-иерархию по
        # объектному имени блока.
        all_configure = [
            b for b in screen.findChildren(QPushButton)
            if b.text() == "Настроить"
        ]
        assert len(all_configure) >= 2  # минимум merger + output

        with qtbot.waitSignal(screen.merger_configure_requested, timeout=1000):
            # Клик по кнопке блока 2 — ищем её через _merger_block
            merger_configure = [
                b for b in screen._merger_block.findChildren(QPushButton)  # noqa: SLF001
                if b.text() == "Настроить"
            ]
            assert len(merger_configure) == 1
            merger_configure[0].click()

    def test_output_configure_button_emits(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)

        with qtbot.waitSignal(screen.output_configure_requested, timeout=1000):
            output_configure = [
                b for b in screen._output_block.findChildren(QPushButton)  # noqa: SLF001
                if b.text() == "Настроить"
            ]
            assert len(output_configure) == 1
            output_configure[0].click()


# ── Phase 6/7: running / done / failed state transitions ─────────────


@pytest.mark.gui
class TestProcessingStates:
    def test_starts_in_idle_state(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)
        # Stack index 0 = idle page
        assert screen._stack.currentIndex() == 0  # noqa: SLF001

    def test_set_state_running_switches_to_page_1(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)
        screen.set_state_running()
        assert screen._stack.currentIndex() == 1  # noqa: SLF001
        # Run button is disabled while running
        assert not screen._run_button.isEnabled()  # noqa: SLF001

    def test_update_stage_advances_progress_bar(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)
        screen.set_state_running()
        screen.update_stage("speech", "gigaam")
        # speech = idx 1 of 6 → ~33%
        assert 20 <= screen._progress_bar.value() <= 40  # noqa: SLF001

        screen.update_stage("render", "plain-text")
        assert screen._progress_bar.value() >= 80  # noqa: SLF001

    def test_update_stage_ignores_unknown(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)
        screen.set_state_running()
        before = screen._progress_bar.value()  # noqa: SLF001
        screen.update_stage("bogus", "ignored")
        assert screen._progress_bar.value() == before  # noqa: SLF001

    def test_set_state_done_switches_to_page_2(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)
        screen.set_state_done("C:/foo/merged.txt")
        assert screen._stack.currentIndex() == 2  # noqa: SLF001
        assert "merged.txt" in screen._done_subtitle.text()  # noqa: SLF001
        assert screen._run_button.isEnabled()  # noqa: SLF001

    def test_set_state_failed_shows_error(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)
        screen.set_state_failed("CUDA out of memory")
        assert screen._stack.currentIndex() == 2  # noqa: SLF001
        assert "CUDA" in screen._done_subtitle.text()  # noqa: SLF001
        assert "Ошибка" in screen._done_title.text()  # noqa: SLF001

    def test_set_state_idle_returns_to_page_0(self, qtbot):
        screen = SessionScreen(_fixture_data())
        qtbot.addWidget(screen)
        screen.set_state_running()
        screen.set_state_idle()
        assert screen._stack.currentIndex() == 0  # noqa: SLF001
        assert screen._run_button.isEnabled()  # noqa: SLF001


# ── Phase 7: per-card highlighting from stage events ────────────────


def _mixed_source_data() -> SessionScreenData:
    """Fixture with one audio + one chat source, matching real sessions."""
    return SessionScreenData(
        project_name="Foo",
        session_name="Bar",
        sources=(
            SourceCardData(title="Аудио", subtitle="gigaam", files=("1.flac",)),
            SourceCardData(title="Foundry VTT чат", subtitle="", files=("c.db",)),
        ),
    )


@pytest.mark.gui
class TestPerCardStates:
    def test_speech_stage_highlights_audio_card(self, qtbot):
        screen = SessionScreen(_mixed_source_data())
        qtbot.addWidget(screen)
        screen.set_state_running()
        screen.update_stage("speech", "gigaam")

        audio_card = screen._source_cards[0]  # noqa: SLF001
        chat_card = screen._source_cards[1]  # noqa: SLF001
        assert audio_card.visual_state == "running"
        assert chat_card.visual_state == "idle"

    def test_chat_stage_highlights_chat_card(self, qtbot):
        screen = SessionScreen(_mixed_source_data())
        qtbot.addWidget(screen)
        screen.set_state_running()
        screen.update_stage("chat", "chat-log.db")

        assert screen._source_cards[1].visual_state == "running"  # noqa: SLF001

    def test_chat_stage_no_chat_log_does_not_highlight(self, qtbot):
        """Pipeline emits chat/"no chat log" when there's no chat file."""
        screen = SessionScreen(_mixed_source_data())
        qtbot.addWidget(screen)
        screen.set_state_running()
        screen.update_stage("chat", "no chat log")

        assert screen._source_cards[1].visual_state == "idle"  # noqa: SLF001

    def test_done_stage_marks_all_cards_done(self, qtbot):
        screen = SessionScreen(_mixed_source_data())
        qtbot.addWidget(screen)
        screen.set_state_running()
        screen.update_stage("done", "merged.txt")

        for card in screen._source_cards:  # noqa: SLF001
            assert card.visual_state == "done"

    def test_failed_marks_all_cards_error(self, qtbot):
        screen = SessionScreen(_mixed_source_data())
        qtbot.addWidget(screen)
        screen.set_state_failed("boom")
        for card in screen._source_cards:  # noqa: SLF001
            assert card.visual_state == "error"

    def test_set_state_idle_clears_card_states(self, qtbot):
        screen = SessionScreen(_mixed_source_data())
        qtbot.addWidget(screen)
        screen.set_state_running()
        screen.update_stage("speech", "gigaam")
        screen.set_state_idle()
        for card in screen._source_cards:  # noqa: SLF001
            assert card.visual_state == "idle"
