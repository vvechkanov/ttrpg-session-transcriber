"""Phase 7 — SourceCard visual state (idle/running/done/error)."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from ui.widgets import SourceCard, SourceCardData


def _data() -> SourceCardData:
    return SourceCardData(
        title="Аудио",
        subtitle="gigaam",
        files=("1.flac", "2.flac"),
        status="ready",
        status_text="готов",
    )


@pytest.mark.gui
class TestVisualState:
    def test_default_state_is_idle(self, qtbot):
        card = SourceCard(_data())
        qtbot.addWidget(card)
        assert card.visual_state == "idle"
        assert "готов" in card._status_chip.text()  # noqa: SLF001

    def test_running_state_updates_chip(self, qtbot):
        card = SourceCard(_data())
        qtbot.addWidget(card)
        card.set_visual_state("running")
        assert card.visual_state == "running"
        assert "в работе" in card._status_chip.text()  # noqa: SLF001

    def test_done_state_updates_chip(self, qtbot):
        card = SourceCard(_data())
        qtbot.addWidget(card)
        card.set_visual_state("done")
        assert card.visual_state == "done"
        assert "готово" in card._status_chip.text()  # noqa: SLF001

    def test_error_state_with_message(self, qtbot):
        card = SourceCard(_data())
        qtbot.addWidget(card)
        card.set_visual_state("error", message="● CUDA OOM")
        assert card.visual_state == "error"
        assert "CUDA" in card._status_chip.text()  # noqa: SLF001

    def test_idle_restores_original_status_text(self, qtbot):
        card = SourceCard(_data())
        qtbot.addWidget(card)
        card.set_visual_state("running")
        card.set_visual_state("idle")
        assert card.visual_state == "idle"
        assert "готов" in card._status_chip.text()  # noqa: SLF001

    def test_transitions_do_not_raise(self, qtbot):
        card = SourceCard(_data())
        qtbot.addWidget(card)
        for state in ("running", "done", "error", "idle", "running", "done"):
            card.set_visual_state(state)  # type: ignore[arg-type]
