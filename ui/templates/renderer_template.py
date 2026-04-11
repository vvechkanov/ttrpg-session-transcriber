"""renderer_template — UI-шаблон для рендереров (Phase 8 stub).

На Phase 8 единственный MVP-рендерер — ``PlainTextRenderer`` —
пишет ``merged.txt``. У него НЕТ пользовательских настроек
(формат файла фиксирован, кодировка UTF-8), поэтому settings
panel показывает read-only preview имени файла и короткую
подсказку «настраивать нечего». Validate пуст, apply_changes —
no-op, has_unsaved_changes всегда False.

Когда появятся другие рендереры (Markdown, HTML, FountainScript
— см. Phase 11+), шаблон расширится соответствующими полями.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ui.shell import theme
from ui.widgets import SourceCard, SourceCardData


@dataclass
class RendererState:
    """Placeholder state; reserved for future per-renderer progress."""


def make_home_card(
    parent: QWidget | None,
    module: Any,
    state: RendererState | None,
    params: dict[str, Any],
) -> QWidget:
    filename = params.get("filename", "merged.txt")
    renderer_id = params.get("renderer_id", "plain-text")
    data = SourceCardData(
        title=f"Вывод: {filename}",
        subtitle=f"Рендерер: {renderer_id}",
        files=(filename,),
        files_hint="Формат: единый текст с таймкодами",
        status="ready",
        status_text="готов",
    )
    return SourceCard(data, parent=parent)


def make_settings_panel(
    parent: QWidget | None,
    module: Any,
    state: RendererState | None,
    params: dict[str, Any],
) -> "RendererSettingsPanel":
    return RendererSettingsPanel(
        module=module,
        state=state or RendererState(),
        params=params,
        parent=parent,
    )


def make_runtime_panel(
    parent: QWidget | None,
    module: Any,
    state: RendererState | None,
    params: dict[str, Any],
) -> QWidget:
    w = QWidget(parent)
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    label = QLabel("Вывод · запись файла", w)
    label.setStyleSheet(
        f"color: {theme.COLOR_FOREGROUND}; "
        f"font-size: {theme.FONT_SIZE_H3_PX}px;"
    )
    layout.addWidget(label)
    layout.addStretch(1)
    return w


class RendererSettingsPanel(QWidget):
    """Read-only форма настроек рендерера.

    Все поля disabled — у PlainTextRenderer нет пользовательских
    настроек, а мультирендереры приедут в Phase 11+.
    """

    changed = Signal()

    def __init__(
        self,
        *,
        module: Any,
        state: RendererState,
        params: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._module = module

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.GAP_MEDIUM_PX)

        fn_label = QLabel("Имя файла вывода", self)
        fn_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        root.addWidget(fn_label)

        self._filename_edit = QLineEdit(self)
        self._filename_edit.setText(str(params.get("filename", "merged.txt")))
        self._filename_edit.setReadOnly(True)
        root.addWidget(self._filename_edit)

        hint = QLabel(
            "Plain-text рендерер не имеет пользовательских настроек.\n"
            "Другие форматы (Markdown, HTML) появятся позже.",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        root.addWidget(hint)
        root.addStretch(1)

    # ── SettingsPanelProtocol ─────────────────────────────────────────

    def validate(self) -> list[str]:
        return []

    def apply_changes(self) -> None:
        # no-op: all fields are read-only in Phase 8
        return None

    def has_unsaved_changes(self) -> bool:
        return False
