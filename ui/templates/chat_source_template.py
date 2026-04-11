"""chat_source_template — UI-шаблон для chat-like источников (Phase 8 stub).

Реализует Module UI Contract из ADR-016 §Template contract для
``FvttChatSource``. На Phase 8 — это минимальный работоспособный
шаблон:

    * :func:`make_home_card` — показывает имя файла чат-лога (если
      обнаружен в ``session_dir``) и количество строк как hint;
    * :func:`make_settings_panel` — форма из двух read-only полей
      (путь до лог-файла, информация про tz_offset) и одного
      спиннера для ручной настройки TZ offset. Validate пуст
      по определению; apply пишет ``module.tz_offset``;
    * :func:`make_runtime_panel` — stub-строка «готово после speech
      stage», детализация в Phase 9+.

Форма реализует ``SettingsPanelProtocol`` (см.
``core.ui_contract``): ``changed`` сигнал + validate / apply_changes /
has_unsaved_changes. Шаблон НЕ импортирует ``sources/*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ui.shell import theme
from ui.widgets import SourceCard, SourceCardData

logger = logging.getLogger(__name__)

_CHAT_FILE_PATTERNS: tuple[str, ...] = ("*.db", "chat-*.txt", "*chat*.log")


@dataclass
class ChatSourceState:
    """Runtime state for the chat template (ADR-016)."""

    session_dir: Path | None = None
    chat_log_path: Path | None = None
    progress: dict[str, Any] = field(default_factory=dict)


# ── Public factory functions ───────────────────────────────────────────


def make_home_card(
    parent: QWidget | None,
    module: Any,
    state: ChatSourceState | None,
    params: dict[str, Any],
) -> QWidget:
    """Home card: title + chat log file name + count hint."""
    chat_log = _find_chat_log(state)
    files = (chat_log.name,) if chat_log is not None else ()
    status = "ready" if chat_log is not None else "warning"
    status_text = "готов" if chat_log is not None else "нет чат-лога"
    files_hint = ""
    if chat_log is not None:
        try:
            lines = chat_log.read_text(encoding="utf-8", errors="ignore").count("\n")
            files_hint = f"{lines} строк"
        except OSError:
            files_hint = ""

    data = SourceCardData(
        title="Чат-лог (Foundry VTT)",
        subtitle="fvtt-chat parser",
        files=files,
        files_hint=files_hint,
        status=status,
        status_text=status_text,
    )
    return SourceCard(data, parent=parent)


def make_settings_panel(
    parent: QWidget | None,
    module: Any,
    state: ChatSourceState | None,
    params: dict[str, Any],
) -> "ChatSourceSettingsPanel":
    return ChatSourceSettingsPanel(
        module=module,
        state=state or ChatSourceState(),
        params=params,
        parent=parent,
    )


def make_runtime_panel(
    parent: QWidget | None,
    module: Any,
    state: ChatSourceState | None,
    params: dict[str, Any],
) -> QWidget:
    """Runtime panel — Phase 8 stub."""
    w = QWidget(parent)
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(theme.GAP_SMALL_PX)
    label = QLabel("Чат · парсинг FVTT chat-log", w)
    label.setStyleSheet(
        f"color: {theme.COLOR_FOREGROUND}; "
        f"font-size: {theme.FONT_SIZE_H3_PX}px;"
    )
    layout.addWidget(label)
    hint = QLabel("Запустится после стадии речи", w)
    hint.setStyleSheet(
        f"color: {theme.COLOR_MUTED_FG}; font-size: {theme.FONT_SIZE_MICRO_PX}px;"
    )
    layout.addWidget(hint)
    layout.addStretch(1)
    return w


# ── Settings panel impl ───────────────────────────────────────────────


class ChatSourceSettingsPanel(QWidget):
    """Минимальная settings-форма для chat source."""

    changed = Signal()

    def __init__(
        self,
        *,
        module: Any,
        state: ChatSourceState,
        params: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._module = module
        self._state = state
        self._params = params

        chat_log = _find_chat_log(state)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.GAP_MEDIUM_PX)

        path_label = QLabel("Файл чат-лога", self)
        path_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        root.addWidget(path_label)

        self._path_edit = QLineEdit(self)
        self._path_edit.setReadOnly(True)
        self._path_edit.setText(str(chat_log) if chat_log is not None else "не найден")
        root.addWidget(self._path_edit)

        tz_label = QLabel("Сдвиг часового пояса (часы)", self)
        tz_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        root.addWidget(tz_label)

        self._tz_spin = QDoubleSpinBox(self)
        self._tz_spin.setRange(-12.0, 14.0)
        self._tz_spin.setSingleStep(0.5)
        self._tz_spin.setDecimals(1)
        initial = float(getattr(module, "tz_offset", None) or 0.0)
        self._tz_spin.setValue(initial)
        self._baseline_tz = initial
        self._tz_spin.valueChanged.connect(lambda _: self.changed.emit())
        root.addWidget(self._tz_spin)

        root.addStretch(1)

    # ── SettingsPanelProtocol ────────────────────────────────────────

    def validate(self) -> list[str]:
        return []

    def apply_changes(self) -> None:
        new_tz = float(self._tz_spin.value())
        self._module.tz_offset = new_tz
        self._baseline_tz = new_tz

    def has_unsaved_changes(self) -> bool:
        return float(self._tz_spin.value()) != self._baseline_tz


# ── Helpers ───────────────────────────────────────────────────────────


def _find_chat_log(state: ChatSourceState | None) -> Path | None:
    """Locate a chat log inside ``session_dir`` or fall back to state."""
    if state is None:
        return None
    if state.chat_log_path is not None and state.chat_log_path.exists():
        return state.chat_log_path
    if state.session_dir is None:
        return None
    for pattern in _CHAT_FILE_PATTERNS:
        for p in sorted(state.session_dir.glob(pattern)):
            return p
    return None
