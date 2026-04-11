"""merger_template — UI-шаблон для мержеров (Phase 8 stub).

Единственный MVP-мержер — ``ScriptMerger`` — имеет один
пользовательский параметр: ``gap_sec`` (пауза, через которую
реплики одного speakera склеиваются в одну). Этого достаточно
для настройки на Phase 8; более сложная схема (выбор алгоритма,
несколько мержеров в цепочке) отложена.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.shell import theme
from ui.widgets import SourceCard, SourceCardData


@dataclass
class MergerState:
    """Pass-through state for the merger template."""

    # Пока ничего не нужно — ADR-016 допускает пустое состояние.
    # Зарезервирован для Phase 9+ (мульти-merger цепочки).


def make_home_card(
    parent: QWidget | None,
    module: Any,
    state: MergerState | None,
    params: dict[str, Any],
) -> QWidget:
    """Минимальная карточка мержера (используется в block 2).

    На Phase 3 session_screen рендерит строку мержера через
    ``MergerRowData``; когда экран перейдёт на resolve_template
    (Phase 9+), эта карточка заменит ручную строку.
    """
    merger_id = params.get("merger_id", "script")
    gap = float(getattr(module, "gap_sec", params.get("gap_sec_default", 1.0)))
    data = SourceCardData(
        title=f"Мержер: {merger_id}",
        subtitle=f"Склейка реплик при паузе ≤ {gap:.1f} сек",
        files=(),
        files_hint="",
        status="ready",
        status_text="готов",
    )
    return SourceCard(data, parent=parent)


def make_settings_panel(
    parent: QWidget | None,
    module: Any,
    state: MergerState | None,
    params: dict[str, Any],
) -> "MergerSettingsPanel":
    return MergerSettingsPanel(
        module=module,
        state=state or MergerState(),
        params=params,
        parent=parent,
    )


def make_runtime_panel(
    parent: QWidget | None,
    module: Any,
    state: MergerState | None,
    params: dict[str, Any],
) -> QWidget:
    w = QWidget(parent)
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    label = QLabel("Мержер · сведение событий", w)
    label.setStyleSheet(
        f"color: {theme.COLOR_FOREGROUND}; "
        f"font-size: {theme.FONT_SIZE_H3_PX}px;"
    )
    layout.addWidget(label)
    layout.addStretch(1)
    return w


class MergerSettingsPanel(QWidget):
    """Форма настроек мержера (единственное поле — gap_sec)."""

    changed = Signal()

    def __init__(
        self,
        *,
        module: Any,
        state: MergerState,
        params: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._module = module

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.GAP_MEDIUM_PX)

        label = QLabel("Макс. пауза для склейки (сек)", self)
        label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        root.addWidget(label)

        self._gap_spin = QDoubleSpinBox(self)
        self._gap_spin.setRange(0.0, 10.0)
        self._gap_spin.setSingleStep(0.1)
        self._gap_spin.setDecimals(1)
        self._gap_spin.setValue(float(getattr(module, "gap_sec", 1.0)))
        self._baseline = float(self._gap_spin.value())
        self._gap_spin.valueChanged.connect(lambda _: self.changed.emit())
        root.addWidget(self._gap_spin)

        hint = QLabel(
            "Если разница между концом одной реплики и началом следующей\n"
            "реплики того же говорящего ≤ этого значения — они склеиваются.",
            self,
        )
        hint.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addStretch(1)

    # ── SettingsPanelProtocol ─────────────────────────────────────────

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self._gap_spin.value() < 0:
            errors.append("Пауза не может быть отрицательной")
        return errors

    def apply_changes(self) -> None:
        new_gap = float(self._gap_spin.value())
        self._module.gap_sec = new_gap
        self._baseline = new_gap

    def has_unsaved_changes(self) -> bool:
        return float(self._gap_spin.value()) != self._baseline
