"""SessionScreen — центральный экран приложения (Screen 3).

Phases 3-7 of ``docs/architecture/ui-qt-migration.md``:

    * Phase 3 — idle state only with fixture data;
    * Phase 6 — running state wired to ``RunController`` stage signals;
    * Phase 7 — done / failed terminal states + source card highlights.

Четыре вертикальных блока (см. ``docs/design/screen-3-session.md`` §3):

    1. Источники — N карточек source-модулей + placeholder «+»
    2. Мержер — одна строка, фиксировано ``timeline-v1``
    3. Обработка — idle / running / done (Phase 3 только idle)
    4. Вывод — один файл ``merged.txt``

Сверху — breadcrumb (project > session) и таб-бар
(``Обработка`` / ``Транскрипт`` / ``Журнал`` / ``Настройки сессии``).
В Phase 3 breadcrumb и таб-бар — фиктивные (хардкод текста, без
навигации).

Экран **не импортирует** ничего из ``sources/``, ``mergers/``,
``renderers/``. Данные приходят через конструктор в виде
:class:`SessionScreenData` — фикстура, которую в Phase 3 собирает
``ui/shell/app.py`` прямо в коде для демонстрации. В Phase 5+ ту же
структуру начнёт заполнять реальный слой pipeline через `to_home_card`
темплейтов.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.shell import theme
from ui.widgets import (
    AddSourcePlaceholder,
    SourceCard,
    SourceCardData,
)


# ── Презентационные данные экрана ──────────────────────────────────────


@dataclass(frozen=True)
class MergerRowData:
    """Данные блока 2 (мержер). В MVP всегда одна строка."""

    title: str = "Мержер: timeline-v1"
    subtitle: str = "Объединение событий по временным меткам"


@dataclass(frozen=True)
class OutputRowData:
    """Данные блока 4 (рендерер)."""

    filename: str = "merged.txt"
    format_hint: str = "Формат: единый текст с таймкодами"
    body_hint: str = "Файл появится после обработки"


@dataclass(frozen=True)
class SessionScreenData:
    """Все данные экрана сессии для Phase 3 (idle).

    В Phase 5+ эту структуру будет собирать хост из реальных модулей
    pipeline через template-контракт. Сейчас это чистая фикстура.
    """

    #: Breadcrumb: проект → сессия
    project_name: str
    session_name: str
    #: Активная вкладка — в Phase 3 только индикатор (навигации ещё нет)
    active_tab: str = "Обработка"
    #: Карточки источников (блок 1)
    sources: tuple[SourceCardData, ...] = field(default_factory=tuple)
    #: Блок 2 — мержер
    merger: MergerRowData = field(default_factory=MergerRowData)
    #: Блок 4 — вывод
    output: OutputRowData = field(default_factory=OutputRowData)


# ── Progress stages (mirrors core.pipeline.PipelineStage) ─────────────
#
# Kept here as a const map so SessionScreen doesn't import from
# core/pipeline directly — the screen stays presentation-only. The
# host (app.py) translates RunController.stage(str, str) into
# SessionScreen.update_stage(stage, message).

_STAGE_ORDER: tuple[str, ...] = ("start", "speech", "chat", "merge", "render", "done")

_STAGE_LABELS: dict[str, str] = {
    "start":  "Запуск…",
    "speech": "Распознавание речи",
    "chat":   "Разбор чат-лога",
    "merge":  "Сведение событий",
    "render": "Запись файла",
    "done":   "Готово",
}


# ── Иконки как текстовые заглушки (до Phase 4 иконочного пакета) ───────
#
# Во избежание зависимости от lucide/Qt resource system в Phase 3
# используем emoji-глифы из системного шрифта. Это временно — в Phase
# 4+ мы перейдём на QIcon через `qtawesome` или свой resource pack
# (решение откладывается).


def _make_icon_label(glyph: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(glyph, parent)
    label.setFixedSize(20, 20)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(
        f"color: {theme.COLOR_ACCENT}; font-size: 16px; background: transparent;"
    )
    return label


# ── Blocks ─────────────────────────────────────────────────────────────


class _BlockFrame(QFrame):
    """Общий стилизованный контейнер блока (1/2/3/4).

    Тонко-обведённая белая карточка с drop-shadow и скруглёнными
    углами — то же что в Figma v1 (``bg-card rounded-xl
    shadow-[0_2px_8px_rgba(107,98,90,0.08)]``).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("blockFrame")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"""
            QFrame#blockFrame {{
                background-color: {theme.COLOR_CARD};
                border: 1px solid {theme.COLOR_BORDER};
                border-radius: {theme.RADIUS_CARD_PX}px;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(theme.SHADOW_CARD_BLUR_RADIUS)
        shadow.setOffset(0, theme.SHADOW_CARD_OFFSET_Y)
        shadow.setColor(QColor(*theme.SHADOW_CARD_RGBA))
        self.setGraphicsEffect(shadow)


# ── Main screen ────────────────────────────────────────────────────────


class SessionScreen(QWidget):
    """Session Detail (Screen 3) в idle состоянии.

    Сигналы:
        source_configure_requested(int): пользователь нажал ``[Настроить]``
            на карточке блока 1. Параметр — индекс карточки в
            ``SessionScreenData.sources``. Хост решает, какой
            SettingsDrawer открыть (в Phase 4+ — через template registry).
        add_source_requested: пользователь нажал placeholder «+ Добавить
            источник» или кнопку «добавить источник» в заголовке блока 1.
        merger_configure_requested: кнопка ``[Настроить]`` блока 2.
        output_configure_requested: кнопка ``[Настроить]`` блока 4.
        run_clicked: большая кнопка ``[▶ Запустить обработку]`` блока 3.
            В Phase 3 хост просто логирует — реальный pipeline заведёт
            Phase 6.

    Конструктор:
        data: :class:`SessionScreenData` — презентационная фикстура
            (Phase 3) или данные, собранные из реальных модулей (Phase 5+).
    """

    source_configure_requested = Signal(int)
    add_source_requested = Signal()
    merger_configure_requested = Signal()
    output_configure_requested = Signal()
    run_clicked = Signal()

    def __init__(
        self,
        data: SessionScreenData,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self.setStyleSheet(f"background-color: {theme.COLOR_BACKGROUND};")

        # Внешний scroll-контейнер, чтобы на узких окнах контент
        # прокручивался вертикально вместо обрезки
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {theme.COLOR_BACKGROUND}; border: none; }}"
        )
        outer.addWidget(self._scroll)

        content = QWidget()
        content.setStyleSheet(f"background-color: {theme.COLOR_BACKGROUND};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 24, 32, 32)
        content_layout.setSpacing(theme.GAP_LARGE_PX)

        # Breadcrumb + tabs
        content_layout.addLayout(self._build_breadcrumb())
        content_layout.addWidget(self._build_tab_bar())

        # 4 блока
        self._sources_block = self._build_sources_block()
        self._merger_block = self._build_merger_block()
        self._processing_block = self._build_processing_block()
        self._output_block = self._build_output_block()

        for block in (
            self._sources_block,
            self._merger_block,
            self._processing_block,
            self._output_block,
        ):
            content_layout.addWidget(block)

        content_layout.addStretch(1)

        self._scroll.setWidget(content)

    # ── Breadcrumb & tabs ──────────────────────────────────────────────

    def _build_breadcrumb(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.GAP_SMALL_PX)

        project = QLabel(self._data.project_name, self)
        project.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_SMALL_PX}px;"
        )
        row.addWidget(project)

        sep = QLabel("›", self)
        sep.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_SMALL_PX}px;"
        )
        row.addWidget(sep)

        session = QLabel(self._data.session_name, self)
        session.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_SMALL_PX}px;"
        )
        row.addWidget(session)
        row.addStretch(1)

        return row

    def _build_tab_bar(self) -> QWidget:
        w = QWidget(self)
        # Нижняя граница под всем таб-баром (заменяет border-bottom
        # из Figma mockup'а — Qt рисует его как часть QSS).
        w.setStyleSheet(
            f"""
            QWidget {{
                background-color: {theme.COLOR_BACKGROUND};
                border-bottom: 1px solid {theme.COLOR_BORDER};
            }}
            """
        )
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(32)

        for tab_name in ("Обработка", "Транскрипт", "Журнал", "Настройки сессии"):
            is_active = tab_name == self._data.active_tab
            btn = QPushButton(tab_name, w)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._tab_stylesheet(active=is_active))
            btn.setEnabled(False)  # Phase 3: навигация заглушена
            row.addWidget(btn)
        row.addStretch(1)

        return w

    @staticmethod
    def _tab_stylesheet(*, active: bool) -> str:
        if active:
            color = theme.COLOR_FOREGROUND
            border = theme.COLOR_ACCENT
        else:
            color = theme.COLOR_MUTED_FG
            border = "transparent"
        return f"""
            QPushButton {{
                color: {color};
                background: transparent;
                border: none;
                border-bottom: 2px solid {border};
                padding: 6px 2px 10px 2px;
                font-size: {theme.FONT_SIZE_BODY_PX}px;
            }}
            QPushButton:disabled {{
                color: {color};
            }}
        """

    # ── Block 1: Sources ──────────────────────────────────────────────

    def _build_sources_block(self) -> _BlockFrame:
        block = _BlockFrame()
        outer = QVBoxLayout(block)
        outer.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
        )
        outer.setSpacing(theme.GAP_MEDIUM_PX)

        # Header row: «ИСТОЧНИКИ» + [+ добавить источник]
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        section_label = QLabel("ИСТОЧНИКИ", block)
        section_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_TINY_PX}px; "
            f"letter-spacing: 1px;"
        )
        header_row.addWidget(section_label)
        header_row.addStretch(1)

        add_button = QPushButton("+  добавить источник", block)
        add_button.setFlat(True)
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.setStyleSheet(
            f"""
            QPushButton {{
                color: {theme.COLOR_FOREGROUND};
                background: transparent;
                border: none;
                padding: 6px 12px;
                border-radius: {theme.RADIUS_BUTTON_PX - 2}px;
                font-size: {theme.FONT_SIZE_BODY_PX}px;
            }}
            QPushButton:hover {{
                background-color: {theme.COLOR_SECONDARY};
            }}
            """
        )
        add_button.clicked.connect(self.add_source_requested.emit)
        header_row.addWidget(add_button)
        outer.addLayout(header_row)

        # Row of cards
        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(theme.GAP_MEDIUM_PX)

        # В Phase 3 SourceCard хранит фикстуру; индекс идёт из enumerate.
        for idx, card_data in enumerate(self._data.sources):
            icon_glyph = "🎙" if "удио" in card_data.title else "💬"
            card = SourceCard(
                card_data,
                icon_widget=_make_icon_label(icon_glyph),
                parent=block,
            )
            card.configure_clicked.connect(
                lambda i=idx: self.source_configure_requested.emit(i)
            )
            cards_row.addWidget(card, stretch=1)

        # Dashed-placeholder «+»
        placeholder = AddSourcePlaceholder(parent=block)
        placeholder.clicked.connect(self.add_source_requested.emit)
        cards_row.addWidget(placeholder, stretch=1)

        outer.addLayout(cards_row)

        return block

    # ── Block 2: Merger ───────────────────────────────────────────────

    def _build_merger_block(self) -> _BlockFrame:
        block = _BlockFrame()
        layout = QHBoxLayout(block)
        layout.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_COMPACT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_COMPACT_PX,
        )
        layout.setSpacing(theme.GAP_MEDIUM_PX)

        layout.addWidget(_make_icon_label("⧖", block))

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        title = QLabel(self._data.merger.title, block)
        title.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_H3_PX}px;"
        )
        texts.addWidget(title)
        subtitle = QLabel(self._data.merger.subtitle, block)
        subtitle.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        texts.addWidget(subtitle)
        layout.addLayout(texts, stretch=1)

        cfg = self._make_ghost_button("Настроить", parent=block)
        cfg.clicked.connect(self.merger_configure_requested.emit)
        layout.addWidget(cfg)

        return block

    # ── Block 3: Processing (idle / running / done) ───────────────────

    def _build_processing_block(self) -> _BlockFrame:
        """Build the processing block with all three state pages.

        The inner area is a :class:`QStackedWidget` with ``idle`` /
        ``running`` / ``done`` pages. The header + footer are static
        (run button is replaced with a status chip + cancel in running
        state, see :meth:`_update_run_button`).
        """
        block = _BlockFrame()
        block.setMinimumHeight(380)
        outer = QVBoxLayout(block)
        outer.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
        )
        outer.setSpacing(theme.GAP_MEDIUM_PX)

        # Header row: «ОБРАБОТКА» + [▶ Запустить обработку]
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        section_label = QLabel("ОБРАБОТКА", block)
        section_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_TINY_PX}px; "
            f"letter-spacing: 1px;"
        )
        header_row.addWidget(section_label)
        header_row.addStretch(1)

        self._run_button = QPushButton("▶  Запустить обработку", block)
        self._run_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_button.setStyleSheet(self._run_button_style(running=False))
        self._run_button.clicked.connect(self.run_clicked.emit)
        header_row.addWidget(self._run_button)
        outer.addLayout(header_row)

        # Stacked pages: idle / running / done
        self._stack = QStackedWidget(block)
        self._stack.addWidget(self._build_idle_page(block))
        self._stack.addWidget(self._build_running_page(block))
        self._stack.addWidget(self._build_done_page(block))
        outer.addWidget(self._stack, stretch=1)

        # Footer: [x] использовать кэши   [очистить кэш сессии]
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, theme.GAP_MEDIUM_PX, 0, 0)
        footer_row.setSpacing(theme.GAP_SMALL_PX)

        cache_label = QLabel("☑  использовать кэши", block)
        cache_label.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_BODY_PX}px;"
        )
        footer_row.addWidget(cache_label)
        footer_row.addStretch(1)

        clear_button = self._make_ghost_button(
            "очистить кэш сессии", parent=block
        )
        clear_button.setEnabled(False)  # Phase 3: заглушка
        footer_row.addWidget(clear_button)

        outer.addLayout(footer_row)

        return block

    def _build_idle_page(self, parent: QWidget) -> QWidget:
        """Page 0 — idle: big circular play-icon hint."""
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.GAP_SMALL_PX)
        layout.addStretch(1)

        circle = QLabel("▶", page)
        circle.setFixedSize(72, 72)
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setStyleSheet(
            f"""
            QLabel {{
                color: {theme.COLOR_ACCENT};
                background-color: rgba(212, 132, 59, 0.10);
                border-radius: 36px;
                font-size: 32px;
            }}
            """
        )
        layout.addWidget(circle, alignment=Qt.AlignmentFlag.AlignHCenter)

        title_hint = QLabel("Нажмите «Запустить», чтобы начать", page)
        title_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_hint.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_H3_PX}px;"
        )
        layout.addWidget(title_hint)

        sub_hint = QLabel("Прогресс каждого источника появится здесь", page)
        sub_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_hint.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_BODY_PX}px;"
        )
        layout.addWidget(sub_hint)

        layout.addStretch(1)
        return page

    def _build_running_page(self, parent: QWidget) -> QWidget:
        """Page 1 — running: determinate progress bar + per-stage list."""
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.GAP_MEDIUM_PX)
        layout.addStretch(1)

        header = QLabel("Обработка сессии", page)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_H3_PX}px;"
        )
        layout.addWidget(header)

        self._progress_bar = QProgressBar(page)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {theme.COLOR_MUTED};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {theme.COLOR_ACCENT};
                border-radius: 4px;
            }}
            """
        )
        layout.addWidget(self._progress_bar)

        self._stage_label = QLabel("Запуск…", page)
        self._stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stage_label.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_BODY_PX}px;"
        )
        layout.addWidget(self._stage_label)

        self._stage_message = QLabel("", page)
        self._stage_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stage_message.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        layout.addWidget(self._stage_message)

        layout.addStretch(1)
        return page

    def _build_done_page(self, parent: QWidget) -> QWidget:
        """Page 2 — done: success tick + output path + open button."""
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.GAP_SMALL_PX)
        layout.addStretch(1)

        circle = QLabel("✓", page)
        circle.setFixedSize(72, 72)
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setStyleSheet(
            f"""
            QLabel {{
                color: {theme.COLOR_ACCENT_FG};
                background-color: {theme.COLOR_SUCCESS};
                border-radius: 36px;
                font-size: 36px;
            }}
            """
        )
        layout.addWidget(circle, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._done_title = QLabel("Готово", page)
        self._done_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._done_title.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_H3_PX}px;"
        )
        layout.addWidget(self._done_title)

        self._done_subtitle = QLabel("", page)
        self._done_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._done_subtitle.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        self._done_subtitle.setWordWrap(True)
        layout.addWidget(self._done_subtitle)

        layout.addStretch(1)
        return page

    # ── Public state transitions (Phase 6+) ───────────────────────────

    def set_state_idle(self) -> None:
        """Return block 3 to the idle placeholder."""
        self._stack.setCurrentIndex(0)
        self._run_button.setText("▶  Запустить обработку")
        self._run_button.setEnabled(True)
        self._run_button.setStyleSheet(self._run_button_style(running=False))

    def set_state_running(self) -> None:
        """Switch block 3 into the running state and reset progress."""
        self._stack.setCurrentIndex(1)
        self._progress_bar.setValue(0)
        self._stage_label.setText(_STAGE_LABELS["start"])
        self._stage_message.setText("")
        self._run_button.setText("● Идёт обработка…")
        self._run_button.setEnabled(False)
        self._run_button.setStyleSheet(self._run_button_style(running=True))

    def update_stage(self, stage: str, message: str = "") -> None:
        """Update running panel for a pipeline stage event.

        Host wires ``RunController.stage`` → this slot.
        """
        if stage not in _STAGE_ORDER:
            return
        idx = _STAGE_ORDER.index(stage)
        # Progress: evenly distributed across stages (0..1)
        value = int(round((idx + 1) / len(_STAGE_ORDER) * 100))
        self._progress_bar.setValue(value)
        self._stage_label.setText(_STAGE_LABELS.get(stage, stage))
        self._stage_message.setText(message)

    def set_state_done(self, output_path: str) -> None:
        """Switch block 3 to the terminal success page."""
        self._stack.setCurrentIndex(2)
        self._done_title.setText("Готово")
        self._done_subtitle.setText(output_path)
        self._run_button.setText("↻  Запустить снова")
        self._run_button.setEnabled(True)
        self._run_button.setStyleSheet(self._run_button_style(running=False))

    def set_state_failed(self, error_text: str) -> None:
        """Switch block 3 to the terminal failure page (reuses done page)."""
        self._stack.setCurrentIndex(2)
        self._done_title.setText("Ошибка обработки")
        self._done_subtitle.setText(error_text)
        self._run_button.setText("↻  Попробовать снова")
        self._run_button.setEnabled(True)
        self._run_button.setStyleSheet(self._run_button_style(running=False))

    @staticmethod
    def _run_button_style(*, running: bool) -> str:
        bg = theme.COLOR_MUTED if running else theme.COLOR_ACCENT
        hover_bg = theme.COLOR_MUTED if running else theme.COLOR_ACCENT_HOVER
        fg = theme.COLOR_MUTED_FG if running else theme.COLOR_ACCENT_FG
        return f"""
            QPushButton {{
                color: {fg};
                background-color: {bg};
                border: none;
                border-radius: {theme.RADIUS_CARD_PX}px;
                padding: 12px 24px;
                font-size: {theme.FONT_SIZE_H3_PX}px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
            }}
            QPushButton:disabled {{
                color: {theme.COLOR_MUTED_FG};
                background-color: {theme.COLOR_MUTED};
            }}
        """

    # ── Block 4: Output ───────────────────────────────────────────────

    def _build_output_block(self) -> _BlockFrame:
        block = _BlockFrame()
        outer = QVBoxLayout(block)
        outer.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
        )
        outer.setSpacing(theme.GAP_MEDIUM_PX)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        section_label = QLabel("ВЫВОД", block)
        section_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_TINY_PX}px; "
            f"letter-spacing: 1px;"
        )
        header_row.addWidget(section_label)
        header_row.addStretch(1)

        cfg = self._make_ghost_button("Настроить", parent=block)
        cfg.clicked.connect(self.output_configure_requested.emit)
        header_row.addWidget(cfg)
        outer.addLayout(header_row)

        file_row = QHBoxLayout()
        file_row.setContentsMargins(0, 0, 0, 0)
        file_row.setSpacing(theme.GAP_MEDIUM_PX)

        file_row.addWidget(_make_icon_label("📄", block))

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        filename = QLabel(self._data.output.filename, block)
        filename.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-family: Consolas, 'Courier New', monospace; "
            f"font-size: {theme.FONT_SIZE_H3_PX}px;"
        )
        texts.addWidget(filename)
        fmt_hint = QLabel(self._data.output.format_hint, block)
        fmt_hint.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        texts.addWidget(fmt_hint)
        file_row.addLayout(texts, stretch=1)
        outer.addLayout(file_row)

        body_hint = QLabel(self._data.output.body_hint, block)
        body_hint.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_BODY_PX}px;"
        )
        outer.addWidget(body_hint)

        return block

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _make_ghost_button(text: str, *, parent: QWidget) -> QPushButton:
        btn = QPushButton(text, parent)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                color: {theme.COLOR_FOREGROUND};
                background: transparent;
                border: none;
                padding: 6px 12px;
                border-radius: {theme.RADIUS_BUTTON_PX - 2}px;
                font-size: {theme.FONT_SIZE_BODY_PX}px;
            }}
            QPushButton:hover {{
                background-color: {theme.COLOR_SECONDARY};
            }}
            QPushButton:disabled {{
                color: {theme.COLOR_MUTED_FG};
            }}
            """
        )
        return btn
