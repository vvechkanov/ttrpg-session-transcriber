"""Demo-заглушка для ручного тестирования SettingsDrawer.

НЕ production-темплейт. В фазе 4 ui-qt-migration реальные темплейты
появятся в ``ui/templates/*_template.py`` и будут реализовывать
``SettingsPanelProtocol`` полноценно. Эта заглушка нужна только чтобы
SettingsDrawer можно было открыть руками из ``ui/shell/app.py`` и
проверить поведение хоста (анимация, dirty-индикатор, save/cancel,
backdrop click, Esc).

Префикс ``_`` в имени модуля — намеренный, чтобы reviewer не путал с
реальными темплейтами.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class DemoStubPanel(QWidget):
    """Минимальная реализация ``SettingsPanelProtocol`` для ручных проверок.

    Один чекбокс + одно текстовое поле. Любое изменение помечает
    панель как dirty. ``validate()`` всегда успешен. ``apply_changes()``
    фиксирует текущие значения как «исходные» (последующие изменения
    снова становятся dirty).
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initial_checked = False
        self._initial_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Это демонстрационная заглушка", self)
        title.setStyleSheet("color: #2D2520; font-size: 16px; font-weight: 500;")
        layout.addWidget(title)

        subtitle = QLabel(
            "В фазе 4 её заменят реальные шаблоны из ui/templates/. "
            "Пока этот виджет нужен только чтобы протестировать SettingsDrawer: "
            "анимацию, dirty-индикатор, save/cancel, закрытие по backdrop/Esc.",
            self,
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #6B625A; font-size: 13px;")
        layout.addWidget(subtitle)

        self._checkbox = QCheckBox("Пример чекбокса", self)
        self._checkbox.toggled.connect(self.changed.emit)
        layout.addWidget(self._checkbox)

        self._line = QLineEdit(self)
        self._line.setPlaceholderText("Пример текстового поля")
        self._line.textChanged.connect(self.changed.emit)
        layout.addWidget(self._line)

        layout.addStretch(1)

    # ── SettingsPanelProtocol ──────────────────────────────────────

    def validate(self) -> list[str]:
        return []

    def apply_changes(self) -> None:
        self._initial_checked = self._checkbox.isChecked()
        self._initial_text = self._line.text()

    def has_unsaved_changes(self) -> bool:
        return (
            self._checkbox.isChecked() != self._initial_checked
            or self._line.text() != self._initial_text
        )
