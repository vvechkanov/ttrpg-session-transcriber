"""SourceCard — идентичная Figma v1 карточка источника для блока 1
Session Detail.

Phase 3 scope (см. ADR-017 / ui-qt-migration §Phase 3): **только idle
состояние**. Running/done состояния (подсветка accent-рамкой, статус
``в работе``, ``dimmed``) добавятся в Phase 6-7 отдельным PR, когда
появятся реальные сигналы прогресса.

Карточка — чисто презентационная: никаких сигналов в реальные модули,
никакого бэкенда. Данные приходят через конструктор, кнопка
``[Настроить]`` эмитит ``configure_clicked``. Хост (``SessionScreen``)
решает, что с этим делать — в Phase 3 пока что просто логирует, а в
Phase 4 начнёт открывать ``SettingsDrawer`` с реальным темплейтом.

Не путать со «stub panel»: ``_demo_stub_panel.py`` — это форма внутри
drawer'а, а ``SourceCard`` — это карточка на главном экране. Разные
паттерны, разный lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.shell import theme

#: Статус карточки — определяет цвет и текст чипа справа внизу.
#: ``ready`` → зелёный «готов», ``warning`` → жёлтый «нужны файлы»,
#: ``error`` → красный «ошибка». Running/running-подсветка добавятся
#: в Phase 6-7 отдельным типом ``running``.
CardStatus = Literal["ready", "warning", "error"]


@dataclass(frozen=True)
class SourceCardData:
    """Презентационные данные карточки источника.

    Хост формирует это из реального модуля (Phase 5+) или из фикстуры
    (Phase 3-4). Namedtuple-подобный immutable dataclass — позволяет
    тестам сравнивать на равенство.
    """

    #: Крупный заголовок, например «Аудио» или «Foundry VTT чат»
    title: str
    #: Подзаголовок под title — backend/config («GigaAM-v3 RNNT · русский»)
    subtitle: str
    #: Список имён входных файлов, отображается моноширинным шрифтом
    files: tuple[str, ...] = ()
    #: Дополнительная строка счётчика («1423 реплики · 12 участников»)
    files_hint: str = ""
    #: Статус карточки (влияет на цвет чипа)
    status: CardStatus = "ready"
    #: Текст статус-чипа
    status_text: str = "готов"


class SourceCard(QFrame):
    """Карточка источника (блок 1 Session Detail).

    Лейаут:
        ┌────────────────────────────────────┐
        │ [icon] Title           [?]          │  ← header row
        │ subtitle                             │
        │                                      │
        │ 📄 1-Andrey.flac                     │  ← files list
        │ 📄 2-Boris.flac                      │
        │ ...                                  │
        │                                      │
        │ [● готов]          [Настроить]       │  ← footer row
        └────────────────────────────────────┘

    Конструктор принимает :class:`SourceCardData` и опционально виджет
    иконки — иконку рисует хост (QLabel с emoji или QIcon), чтобы
    карточка не зависела от иконочного набора.

    Сигналы:
        configure_clicked: пользователь нажал ``[Настроить]``.
    """

    configure_clicked = Signal()

    def __init__(
        self,
        data: SourceCardData,
        *,
        icon_widget: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data

        self.setObjectName("sourceCard")
        self.setStyleSheet(self._card_stylesheet())
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._apply_drop_shadow()

        root = QVBoxLayout(self)
        root.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
        )
        root.setSpacing(theme.GAP_MEDIUM_PX)

        root.addLayout(self._build_header_row(icon_widget))
        root.addWidget(self._build_files_block(), stretch=1)
        root.addLayout(self._build_footer_row())

    # ── Layout builders ────────────────────────────────────────────────

    def _build_header_row(self, icon_widget: QWidget | None) -> QVBoxLayout:
        """Заголовок карточки: иконка + title (одна строка), subtitle ниже."""
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(theme.GAP_SMALL_PX)

        if icon_widget is not None:
            icon_widget.setParent(self)
            title_row.addWidget(icon_widget, alignment=Qt.AlignmentFlag.AlignVCenter)

        title_label = QLabel(self._data.title, self)
        title_label.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_H3_PX}px; "
            f"font-weight: 500;"
        )
        title_row.addWidget(title_label)
        title_row.addStretch(1)

        col.addLayout(title_row)

        subtitle_label = QLabel(self._data.subtitle or "\u00a0", self)
        subtitle_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        col.addWidget(subtitle_label)

        return col

    def _build_files_block(self) -> QWidget:
        """Список входных файлов моноширинным шрифтом + опциональный hint."""
        w = QWidget(self)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        for name in self._data.files:
            row = QLabel(f"📄  {name}", w)
            row.setStyleSheet(
                f"color: {theme.COLOR_FOREGROUND}; "
                f"font-family: Consolas, 'Courier New', monospace; "
                f"font-size: {theme.FONT_SIZE_BODY_PX}px;"
            )
            layout.addWidget(row)

        if self._data.files_hint:
            hint = QLabel(self._data.files_hint, w)
            hint.setContentsMargins(20, 0, 0, 0)
            hint.setStyleSheet(
                f"color: {theme.COLOR_MUTED_FG}; "
                f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
            )
            layout.addWidget(hint)

        layout.addStretch(1)
        return w

    def _build_footer_row(self) -> QHBoxLayout:
        """Низ карточки: статус-чип слева, ``[Настроить]`` справа."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.GAP_SMALL_PX)

        chip = QLabel(f"● {self._data.status_text}", self)
        chip.setStyleSheet(self._chip_stylesheet(self._data.status))
        row.addWidget(chip)
        row.addStretch(1)

        self._configure_button = QPushButton("Настроить", self)
        self._configure_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._configure_button.setFlat(True)
        self._configure_button.setStyleSheet(self._configure_button_stylesheet())
        self._configure_button.clicked.connect(self.configure_clicked.emit)
        row.addWidget(self._configure_button)

        return row

    # ── Styling ─────────────────────────────────────────────────────────

    @staticmethod
    def _card_stylesheet() -> str:
        return f"""
            QFrame#sourceCard {{
                background-color: {theme.COLOR_CARD};
                border: 1px solid {theme.COLOR_BORDER};
                border-radius: {theme.RADIUS_CARD_PX}px;
            }}
        """

    @staticmethod
    def _chip_stylesheet(status: CardStatus) -> str:
        # Цвет чипа зависит только от статуса. Фон — бледная обводка
        # accent-цвета статуса (как в Figma v1).
        if status == "warning":
            bg = "rgba(217, 156, 49, 0.12)"
            fg = "#A06A1A"
        elif status == "error":
            bg = "rgba(185, 56, 52, 0.12)"
            fg = "#B93834"
        else:
            bg = "rgba(90, 138, 62, 0.12)"
            fg = theme.COLOR_SUCCESS
        return (
            f"QLabel {{"
            f" color: {fg};"
            f" background-color: {bg};"
            f" border-radius: {theme.RADIUS_CHIP_PX}px;"
            f" padding: 4px 10px;"
            f" font-size: {theme.FONT_SIZE_MICRO_PX}px;"
            f" }}"
        )

    @staticmethod
    def _configure_button_stylesheet() -> str:
        return f"""
            QPushButton {{
                color: {theme.COLOR_FOREGROUND};
                background-color: transparent;
                border: none;
                padding: 6px 12px;
                border-radius: {theme.RADIUS_BUTTON_PX - 2}px;
                font-size: {theme.FONT_SIZE_BODY_PX}px;
            }}
            QPushButton:hover {{
                background-color: {theme.COLOR_SECONDARY};
            }}
        """

    def _apply_drop_shadow(self) -> None:
        """Qt не умеет CSS box-shadow, навешиваем QGraphicsDropShadowEffect."""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(theme.SHADOW_CARD_BLUR_RADIUS)
        shadow.setOffset(0, theme.SHADOW_CARD_OFFSET_Y)
        shadow.setColor(QColor(*theme.SHADOW_CARD_RGBA))
        self.setGraphicsEffect(shadow)


@dataclass(frozen=True)
class AddSourcePlaceholderData:
    """Пустая карточка-плейсхолдер «+ Добавить источник» в блоке 1.

    Появляется как последняя карточка в блоке 1, когда экран находится
    в idle. Phase 3 — только презентация, клик на ней Phase 4+ откроет
    меню выбора типа источника.
    """

    title: str = "Добавить источник"
    hint: str = "Аудио, чат или другой парсер"
    files: tuple[str, ...] = field(default_factory=tuple)


class AddSourcePlaceholder(QFrame):
    """Dashed-бордюр карточка с плюсом в центре."""

    clicked = Signal()

    def __init__(
        self,
        data: AddSourcePlaceholderData | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data or AddSourcePlaceholderData()

        self.setObjectName("addSourcePlaceholder")
        self.setStyleSheet(
            f"""
            QFrame#addSourcePlaceholder {{
                background-color: transparent;
                border: 2px dashed {theme.COLOR_BORDER};
                border-radius: {theme.RADIUS_CARD_PX}px;
            }}
            """
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
        )
        root.setSpacing(theme.GAP_SMALL_PX)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        plus = QLabel("+", self)
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus.setFixedSize(48, 48)
        plus.setStyleSheet(
            f"""
            QLabel {{
                color: {theme.COLOR_MUTED_FG};
                background-color: {theme.COLOR_SECONDARY};
                border-radius: 24px;
                font-size: 28px;
            }}
            """
        )
        root.addWidget(plus, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(self._data.title, self)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_BODY_PX}px;"
        )
        root.addWidget(title)

        hint = QLabel(self._data.hint, self)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        root.addWidget(hint)

    def mousePressEvent(self, event) -> None:  # noqa: D401 — Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
