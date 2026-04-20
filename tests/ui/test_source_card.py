"""Phase 7 — SourceCard visual state (idle/running/done/error)
and P3 — tri-state display (files / drop / choose) + drop validation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QCheckBox, QPushButton  # noqa: E402

from ui.widgets import SourceCard, SourceCardData  # noqa: E402


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


# ── P3 — tri-state display (files / drop / choose) ────────────────────


@pytest.mark.gui
class TestStateA:
    def test_default_display_state_is_files(self, qtbot):
        card = SourceCard(_data())
        qtbot.addWidget(card)
        assert card.display_state == "files"

    def test_files_header_mentions_count(self, qtbot):
        """State A should show "Автоматически нашёл N" copy."""
        card = SourceCard(_data())
        qtbot.addWidget(card)
        from PySide6.QtWidgets import QLabel
        labels = [lb.text() for lb in card.findChildren(QLabel)]
        assert any("Автоматически" in t for t in labels)


@pytest.mark.gui
class TestStateB:
    def _drop_data(self) -> SourceCardData:
        return SourceCardData(
            title="Foundry VTT чат",
            subtitle="fvtt-chat parser",
            files=(),
            missing_hint="fvtt-log-*.txt",
            parser_key="fvtt-chat",
        )

    def test_display_state_is_drop_when_no_files_and_hint(self, qtbot):
        card = SourceCard(self._drop_data())
        qtbot.addWidget(card)
        assert card.display_state == "drop"

    def test_drop_zone_has_pick_button(self, qtbot):
        card = SourceCard(self._drop_data())
        qtbot.addWidget(card)
        pick = [
            b for b in card.findChildren(QPushButton)
            if "Выбрать файл" in b.text()
        ]
        assert len(pick) == 1

    def test_missing_hint_visible(self, qtbot):
        card = SourceCard(self._drop_data())
        qtbot.addWidget(card)
        from PySide6.QtWidgets import QLabel
        labels = [lb.text() for lb in card.findChildren(QLabel)]
        assert any("fvtt-log-*.txt" in t for t in labels)


@pytest.mark.gui
class TestStateC:
    def _choose_data(
        self,
        candidates: tuple[str, ...] = ("Бой_дракон.json", "Бой_гоблины.json", "combat_old.json"),
        selected: tuple[str, ...] = ("Бой_дракон.json", "Бой_гоблины.json"),
    ) -> SourceCardData:
        return SourceCardData(
            title="Бой",
            subtitle="FVTT encounter",
            files=(),
            candidate_files=candidates,
            selected_candidates=selected,
            parser_key="fvtt-chat",
        )

    def test_display_state_is_choose_when_multiple_candidates(self, qtbot):
        card = SourceCard(self._choose_data())
        qtbot.addWidget(card)
        assert card.display_state == "choose"

    def test_renders_one_checkbox_per_candidate(self, qtbot):
        card = SourceCard(self._choose_data())
        qtbot.addWidget(card)
        checkboxes = card.findChildren(QCheckBox)
        assert len(checkboxes) == 3

    def test_preselection_reflects_selected_candidates(self, qtbot):
        card = SourceCard(self._choose_data())
        qtbot.addWidget(card)
        checked = {
            cb.text() for cb in card.findChildren(QCheckBox) if cb.isChecked()
        }
        assert checked == {"Бой_дракон.json", "Бой_гоблины.json"}

    def test_candidate_toggled_signal_emits(self, qtbot):
        card = SourceCard(self._choose_data())
        qtbot.addWidget(card)

        received: list[tuple[str, bool]] = []
        card.candidate_toggled.connect(
            lambda name, checked: received.append((name, checked))
        )

        # Find the checkbox for "combat_old.json" (initially unchecked)
        target = next(
            cb for cb in card.findChildren(QCheckBox)
            if cb.text() == "combat_old.json"
        )
        target.setChecked(True)

        assert ("combat_old.json", True) in received


@pytest.mark.gui
class TestFileDrop:
    def test_valid_file_emits_file_dropped(self, qtbot, tmp_path: Path):
        data = SourceCardData(
            title="Аудио",
            subtitle="gigaam",
            parser_key="gigaam",
        )
        card = SourceCard(data)
        qtbot.addWidget(card)

        audio_path = tmp_path / "sample.flac"
        audio_path.write_bytes(b"")

        received: list[str] = []
        card.file_dropped.connect(received.append)

        accepted = card.handle_dropped_path(audio_path)

        assert accepted is True
        assert received == [str(audio_path)]

    def test_invalid_file_does_not_emit(self, qtbot, tmp_path: Path):
        data = SourceCardData(
            title="Foundry VTT чат",
            subtitle="fvtt-chat parser",
            parser_key="fvtt-chat",
        )
        card = SourceCard(data)
        qtbot.addWidget(card)

        wrong_path = tmp_path / "track.mp3"
        wrong_path.write_bytes(b"")

        received: list[str] = []
        card.file_dropped.connect(received.append)

        accepted = card.handle_dropped_path(wrong_path)

        assert accepted is False
        assert received == []
        # Warning was captured so the UI can surface the message.
        assert card.last_invalid_drop_message is not None
        assert ".txt" in card.last_invalid_drop_message

    def test_unknown_parser_key_rejects_everything(self, qtbot, tmp_path: Path):
        data = SourceCardData(
            title="Неизвестный",
            subtitle="",
            parser_key="nonexistent",
        )
        card = SourceCard(data)
        qtbot.addWidget(card)

        path = tmp_path / "anything.flac"
        path.write_bytes(b"")

        received: list[str] = []
        card.file_dropped.connect(received.append)

        accepted = card.handle_dropped_path(path)
        assert accepted is False
        assert received == []

    def test_empty_parser_key_accepts_anything(self, qtbot, tmp_path: Path):
        """When parser_key is not set (legacy cards), validation is off.

        This keeps :class:`SourceCardData` instances built by older code
        paths working — the new drop feature is opt-in via parser_key.
        """
        data = SourceCardData(title="Legacy", subtitle="")
        card = SourceCard(data)
        qtbot.addWidget(card)

        path = tmp_path / "whatever.xyz"
        path.write_bytes(b"")

        received: list[str] = []
        card.file_dropped.connect(received.append)

        accepted = card.handle_dropped_path(path)
        assert accepted is True
        assert received == [str(path)]


@pytest.mark.gui
class TestRemoveButton:
    def test_remove_button_visible_by_default(self, qtbot):
        card = SourceCard(_data())
        qtbot.addWidget(card)
        # Default removable=True
        buttons = [b.text() for b in card.findChildren(QPushButton)]
        assert "×" in buttons

    def test_remove_button_hidden_when_not_removable(self, qtbot):
        data = SourceCardData(
            title="Аудио",
            subtitle="gigaam",
            files=("1.flac",),
            removable=False,
        )
        card = SourceCard(data)
        qtbot.addWidget(card)
        buttons = [b.text() for b in card.findChildren(QPushButton)]
        assert "×" not in buttons

    def test_remove_click_emits_signal(self, qtbot):
        card = SourceCard(_data())
        qtbot.addWidget(card)

        remove_btn = next(
            b for b in card.findChildren(QPushButton) if b.text() == "×"
        )

        with qtbot.waitSignal(card.remove_clicked, timeout=1000):
            remove_btn.click()
