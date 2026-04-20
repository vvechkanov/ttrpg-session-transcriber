"""SourceCard — Figma v1 карточка источника для блока 1 Session Detail.

Phase 3 landed the idle state; Phase 7 added **visual running / done /
failed** states driven by :meth:`SourceCard.set_visual_state`; P3
adds **tri-state display** driven by what
:mod:`core.file_matchers` found in the session folder for this
parser:

    * State A — one or more files matched the parser's pattern;
    * State B — nothing matched; an in-card drop zone asks the user
      to drop or pick a file;
    * State C — multiple candidates matched; checkboxes let the user
      pick which ones to feed the parser.

The card stays presentational — the host (``SessionScreen`` / ``app``)
decides what each state means for the pipeline. Card signals
(``file_dropped``, ``candidate_toggled``, ``remove_clicked``) are
routed back to the host, which is the only thing that mutates
:class:`SessionScreenData`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from core.file_matchers import accepted_extensions_for, accepts_file_for
from ui.shell import theme

#: Статус карточки — определяет цвет и текст чипа справа внизу.
#: ``ready`` → зелёный «готов», ``warning`` → жёлтый «нужны файлы»,
#: ``error`` → красный «ошибка».
CardStatus = Literal["ready", "warning", "error"]

#: Визуальное состояние карточки при рантайме pipeline (Phase 7).
#: Хост вызывает :meth:`SourceCard.set_visual_state` при получении
#: stage-событий от ``RunController``: когда источник активно
#: обрабатывается — ``running``; когда успех — ``done``; ошибка —
#: ``error``. ``idle`` возвращает карточку к презентации из
#: ``SourceCardData.status``.
CardVisualState = Literal["idle", "running", "done", "error"]

#: Три display-состояния карточки (P3).
#: ``"files"`` — State A, список уже найденных файлов;
#: ``"drop"``  — State B, пусто + drop zone;
#: ``"choose"`` — State C, чекбоксы по кандидатам.
CardDisplayState = Literal["files", "drop", "choose"]


@dataclass(frozen=True)
class SourceCardData:
    """Презентационные данные карточки источника.

    Хост формирует это из реального модуля (Phase 5+) или из фикстуры
    (Phase 3-4). Namedtuple-подобный immutable dataclass — позволяет
    тестам сравнивать на равенство.

    P3 added four optional fields — all default to backwards-compatible
    values so existing call sites keep working:

        * ``candidate_files`` + ``selected_candidates`` — State C;
        * ``missing_hint`` — State B;
        * ``parser_key`` — needed by
          :func:`core.file_matchers.accepts_file_for` to validate a
          dropped file against what the parser can read;
        * ``removable`` — whether to render the "×" remove button.
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
    #: State C — все найденные кандидаты (если > 1, рендерим чекбоксы)
    candidate_files: tuple[str, ...] = ()
    #: State C — какие из ``candidate_files`` отмечены галочкой
    selected_candidates: tuple[str, ...] = ()
    #: State B — короткая подсказка (например, ``"fvtt-log-*.txt"``)
    #: отображается над drop zone, когда файлов не нашли
    missing_hint: str = ""
    #: Ключ парсера, используется для валидации drop-payload
    parser_key: str = ""
    #: Показывать ли кнопку «×» в футере (default True — любую карточку
    #: можно удалить; для default-аудио хост может выставить False).
    removable: bool = True


def _resolve_display_state(data: SourceCardData) -> CardDisplayState:
    """Translate a :class:`SourceCardData` into a display state enum.

    Rules (matches P3 spec §"State resolution"):
        * ``len(candidate_files) > 1`` → ``"choose"`` (State C);
        * otherwise no ``files`` and a non-empty ``missing_hint`` →
          ``"drop"`` (State B);
        * otherwise ``"files"`` (State A).
    """
    if len(data.candidate_files) > 1:
        return "choose"
    if not data.files and data.missing_hint:
        return "drop"
    return "files"


class SourceCard(QFrame):
    """Карточка источника (блок 1 Session Detail).

    Лейаут (State A — files found):

        ┌────────────────────────────────────┐
        │ [icon] Title           [?]          │  ← header row
        │ subtitle                             │
        │                                      │
        │ Автоматически нашёл N файлов:        │  ← header hint (if any)
        │ 📄 1-Andrey.flac                     │  ← files list
        │ 📄 2-Boris.flac                      │
        │                                      │
        │ [● готов]   [Настроить] [×]          │  ← footer row
        └────────────────────────────────────┘

    State B (drop zone) and State C (checkboxes) swap the middle
    files block for the matching layout. Header / footer stay the
    same — the ``×`` button and ``Настроить`` still apply.

    Конструктор принимает :class:`SourceCardData` и опционально виджет
    иконки — иконку рисует хост (QLabel с emoji или QIcon), чтобы
    карточка не зависела от иконочного набора.

    Сигналы:
        configure_clicked: пользователь нажал ``[Настроить]``.
        remove_clicked: пользователь нажал «×» (только если
            ``data.removable`` is True).
        file_dropped(str): в карточку бросили / выбрали через
            диалог валидный файл. Payload — абсолютный путь.
        candidate_toggled(str, bool): пользователь переключил
            чекбокс в State C. ``(filename, checked)``.
    """

    configure_clicked = Signal()
    remove_clicked = Signal()
    file_dropped = Signal(str)
    candidate_toggled = Signal(str, bool)

    def __init__(
        self,
        data: SourceCardData,
        *,
        icon_widget: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._visual_state: CardVisualState = "idle"
        self._display_state: CardDisplayState = _resolve_display_state(data)

        self.setObjectName("sourceCard")
        self.setStyleSheet(self._card_stylesheet("idle"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._apply_drop_shadow()
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
        )
        root.setSpacing(theme.GAP_MEDIUM_PX)

        root.addLayout(self._build_header_row(icon_widget))
        root.addWidget(self._build_body_block(), stretch=1)
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

    def _build_body_block(self) -> QWidget:
        """Switch between State A / B / C for the card's middle area."""
        if self._display_state == "choose":
            return self._build_choose_block()
        if self._display_state == "drop":
            return self._build_drop_block()
        return self._build_files_block()

    def _build_files_block(self) -> QWidget:
        """State A — auto-found files list (+ optional hint)."""
        w = QWidget(self)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        n_files = len(self._data.files)
        if n_files > 0:
            header = QLabel(f"Автоматически нашёл {n_files} {_plural_files(n_files)}:", w)
            header.setStyleSheet(
                f"color: {theme.COLOR_MUTED_FG}; "
                f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
            )
            layout.addWidget(header)

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

    def _build_drop_block(self) -> QWidget:
        """State B — missing-files hint + dashed drop zone + pick button."""
        w = QWidget(self)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.GAP_SMALL_PX)

        # The missing_hint is a short pattern like "fvtt-log-*.txt". We
        # wrap it in a user-visible warning line so the card explains
        # why the drop zone is there.
        warn_text = f"⚠  Не нашёл файл по маске `{self._data.missing_hint}`"
        warn = QLabel(warn_text, w)
        warn.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        warn.setWordWrap(True)
        layout.addWidget(warn)

        drop_frame = QFrame(w)
        drop_frame.setObjectName("sourceCardDropZone")
        drop_frame.setStyleSheet(
            f"""
            QFrame#sourceCardDropZone {{
                background-color: transparent;
                border: 2px dashed {theme.COLOR_BORDER};
                border-radius: 10px;
            }}
            """
        )
        drop_layout = QVBoxLayout(drop_frame)
        drop_layout.setContentsMargins(16, 20, 16, 20)
        drop_layout.setSpacing(theme.GAP_SMALL_PX)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        prompt = QLabel("перетащите файл сюда", drop_frame)
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prompt.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_BODY_PX}px;"
        )
        drop_layout.addWidget(prompt)

        or_label = QLabel("или", drop_frame)
        or_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        or_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        drop_layout.addWidget(or_label)

        self._pick_button = QPushButton("Выбрать файл…", drop_frame)
        self._pick_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pick_button.setStyleSheet(
            f"""
            QPushButton {{
                color: {theme.COLOR_ACCENT_FG};
                background-color: {theme.COLOR_ACCENT};
                border: none;
                border-radius: {theme.RADIUS_BUTTON_PX}px;
                padding: 6px 14px;
                font-size: {theme.FONT_SIZE_BODY_PX}px;
            }}
            QPushButton:hover {{
                background-color: {theme.COLOR_ACCENT_HOVER};
            }}
            """
        )
        self._pick_button.clicked.connect(self._on_pick_clicked)
        drop_layout.addWidget(
            self._pick_button, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        layout.addWidget(drop_frame, stretch=1)
        return w

    def _build_choose_block(self) -> QWidget:
        """State C — "found N candidates" header + per-file checkboxes."""
        w = QWidget(self)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        n = len(self._data.candidate_files)
        header = QLabel(f"Нашёл {n} {_plural_files(n)} — отметь нужные:", w)
        header.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        layout.addWidget(header)

        self._candidate_checkboxes: dict[str, QCheckBox] = {}
        selected_set = set(self._data.selected_candidates)
        for name in self._data.candidate_files:
            cb = QCheckBox(name, w)
            cb.setChecked(name in selected_set)
            cb.setStyleSheet(
                f"color: {theme.COLOR_FOREGROUND}; "
                f"font-family: Consolas, 'Courier New', monospace; "
                f"font-size: {theme.FONT_SIZE_BODY_PX}px;"
            )
            cb.toggled.connect(
                lambda checked, filename=name: self.candidate_toggled.emit(
                    filename, checked
                )
            )
            layout.addWidget(cb)
            self._candidate_checkboxes[name] = cb

        hint = QLabel("(можно перетащить другой файл)", w)
        hint.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        layout.addWidget(hint)

        layout.addStretch(1)
        return w

    def _build_footer_row(self) -> QHBoxLayout:
        """Низ карточки: статус-чип слева, ``[Настроить]`` + ``×`` справа."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.GAP_SMALL_PX)

        self._status_chip = QLabel(f"● {self._data.status_text}", self)
        self._status_chip.setStyleSheet(self._chip_stylesheet(self._data.status))
        row.addWidget(self._status_chip)
        row.addStretch(1)

        self._configure_button = QPushButton("Настроить", self)
        self._configure_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._configure_button.setFlat(True)
        self._configure_button.setStyleSheet(self._configure_button_stylesheet())
        self._configure_button.clicked.connect(self.configure_clicked.emit)
        row.addWidget(self._configure_button)

        if self._data.removable:
            self._remove_button = QPushButton("×", self)
            self._remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._remove_button.setFlat(True)
            self._remove_button.setToolTip("Убрать источник")
            self._remove_button.setFixedWidth(28)
            self._remove_button.setStyleSheet(self._remove_button_stylesheet())
            self._remove_button.clicked.connect(self.remove_clicked.emit)
            row.addWidget(self._remove_button)

        return row

    # ── Drag and drop (P3) ────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """Accept single-file drags so :meth:`dropEvent` can validate."""
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            event.ignore()
            return
        urls = mime.urls()
        if len(urls) != 1:
            event.ignore()
            return
        path_str = urls[0].toLocalFile()
        if not path_str or not Path(path_str).is_file():
            event.ignore()
            return
        event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        self.dragEnterEvent(event)  # same filter — delegate for simplicity

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """Validate the dropped file against the parser and emit signal.

        A valid file emits :attr:`file_dropped` with the absolute path
        as a string. An invalid extension shows a :class:`QToolTip`
        warning near the card so the user understands why nothing
        happened, and the event is ignored.
        """
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            event.ignore()
            return
        urls = mime.urls()
        if len(urls) != 1:
            event.ignore()
            return
        path_str = urls[0].toLocalFile()
        if not path_str:
            event.ignore()
            return
        path = Path(path_str)
        if not path.is_file():
            event.ignore()
            return

        self._handle_incoming_file(path, accepting_event=event)

    def handle_dropped_path(self, path: Path) -> bool:
        """Testable entry point for drag-and-drop validation.

        Returns ``True`` iff the file passed validation and
        ``file_dropped`` was emitted. Synthesising a real
        :class:`QDropEvent` from Python is fragile, so tests can call
        this method directly with a plain :class:`Path`.
        """
        return self._handle_incoming_file(path, accepting_event=None)

    def _handle_incoming_file(
        self,
        path: Path,
        *,
        accepting_event: QDropEvent | None,
    ) -> bool:
        """Common path for drop events and the file-picker button.

        Returns ``True`` on success (``file_dropped`` emitted), else
        ``False``. The caller decides whether to accept the originating
        event — drops pass it in so we can call
        :meth:`QDropEvent.acceptProposedAction`; the file picker
        passes ``None``.
        """
        parser_key = self._data.parser_key
        if parser_key and not accepts_file_for(parser_key, path):
            self._flash_warning_for_invalid(path)
            if accepting_event is not None:
                accepting_event.ignore()
            return False
        self._last_invalid_message: str | None = None
        if accepting_event is not None:
            accepting_event.acceptProposedAction()
        self.file_dropped.emit(str(path))
        return True

    def _flash_warning_for_invalid(self, path: Path) -> None:
        """Show a tooltip explaining why ``path`` was rejected.

        We also stash the last message on the widget so tests can
        assert on it without having to screen-scrape Qt's tooltip
        runtime (which only renders when a cursor is over the widget).
        """
        accepted = accepted_extensions_for(self._data.parser_key)
        if accepted:
            accepted_desc = " / ".join(accepted)
            message = (
                f"Этот парсер принимает только {accepted_desc}. "
                f"Получен: {path.suffix or '(без расширения)'}"
            )
        else:
            message = "Этот парсер не принимает файлы."
        self._last_invalid_message = message
        # Anchor the tooltip under the card — ``mapToGlobal`` converts
        # a widget-local point to screen coordinates.
        pos = self.mapToGlobal(self.rect().bottomLeft())
        QToolTip.showText(pos, message, self)

    @property
    def last_invalid_drop_message(self) -> str | None:
        """Most recent warning message from an invalid drop, or None."""
        return getattr(self, "_last_invalid_message", None)

    def _on_pick_clicked(self) -> None:
        """File-picker button handler for State B."""
        accepted = accepted_extensions_for(self._data.parser_key)
        if accepted:
            filter_str = (
                f"{self._data.title} ({' '.join('*' + ext for ext in accepted)})"
            )
        else:
            filter_str = "Все файлы (*)"
        picked, _ = QFileDialog.getOpenFileName(
            self,
            f"Выбрать файл — {self._data.title}",
            "",
            filter_str,
        )
        if not picked:
            return
        self._handle_incoming_file(Path(picked), accepting_event=None)

    # ── Public state accessors ────────────────────────────────────────

    @property
    def display_state(self) -> CardDisplayState:
        """Current :data:`CardDisplayState` — derived from ``data``."""
        return self._display_state

    # ── Runtime state (Phase 7) ────────────────────────────────────────

    @property
    def visual_state(self) -> CardVisualState:
        """Current runtime visual state (see :data:`CardVisualState`)."""
        return self._visual_state

    def set_visual_state(
        self,
        state: CardVisualState,
        *,
        message: str | None = None,
    ) -> None:
        """Switch the card's runtime visualisation.

        Args:
            state: one of ``idle`` / ``running`` / ``done`` / ``error``.
            message: optional override for the status chip text. When
                ``None``, the chip falls back to a sensible default
                (``"в работе"`` / ``"готово"`` / ``"ошибка"``) or the
                idle ``SourceCardData.status_text``.
        """
        self._visual_state = state
        self.setStyleSheet(self._card_stylesheet(state))

        chip_text, chip_style_state = self._chip_for_state(state, message)
        self._status_chip.setText(chip_text)
        self._status_chip.setStyleSheet(
            self._chip_stylesheet_for_visual(chip_style_state)
        )

    def _chip_for_state(
        self, state: CardVisualState, message: str | None
    ) -> tuple[str, str]:
        """Resolve (chip_text, style_status) for the given visual state."""
        if state == "running":
            return (message or "● в работе", "running")
        if state == "done":
            return (message or "● готово", "success")
        if state == "error":
            return (message or "● ошибка", "error")
        # idle — fall back to the dataclass status
        return (f"● {self._data.status_text}", self._data.status)

    # ── Styling ─────────────────────────────────────────────────────────

    @staticmethod
    def _card_stylesheet(state: CardVisualState = "idle") -> str:
        # Outer border colour changes by state; everything else stays
        # the same so the card silhouette doesn't jitter.
        if state == "running":
            border = theme.COLOR_ACCENT
            border_width = "2px"
        elif state == "done":
            border = theme.COLOR_SUCCESS
            border_width = "2px"
        elif state == "error":
            border = "#B93834"
            border_width = "2px"
        else:
            border = theme.COLOR_BORDER
            border_width = "1px"
        return f"""
            QFrame#sourceCard {{
                background-color: {theme.COLOR_CARD};
                border: {border_width} solid {border};
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
    def _chip_stylesheet_for_visual(status: str) -> str:
        """Extended chip palette covering runtime states (Phase 7)."""
        if status == "running":
            bg = "rgba(212, 132, 59, 0.14)"
            fg = theme.COLOR_ACCENT
        elif status == "success":
            bg = "rgba(90, 138, 62, 0.14)"
            fg = theme.COLOR_SUCCESS
        elif status == "error":
            bg = "rgba(185, 56, 52, 0.14)"
            fg = "#B93834"
        elif status == "warning":
            bg = "rgba(217, 156, 49, 0.12)"
            fg = "#A06A1A"
        else:  # "ready" or any CardStatus
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

    @staticmethod
    def _remove_button_stylesheet() -> str:
        return f"""
            QPushButton {{
                color: {theme.COLOR_MUTED_FG};
                background-color: transparent;
                border: none;
                padding: 4px 6px;
                border-radius: {theme.RADIUS_BUTTON_PX - 2}px;
                font-size: {theme.FONT_SIZE_H3_PX}px;
            }}
            QPushButton:hover {{
                color: #B93834;
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


def _plural_files(n: int) -> str:
    """Return the Russian plural form of "файл" for ``n``.

    Used only for micro-copy in the card header; we spell out the
    three common cases (1 / 2-4 / other) because Python's ngettext
    needs a .po file for Russian and this single string isn't worth
    the infrastructure.
    """
    if n % 10 == 1 and n % 100 != 11:
        return "файл"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "файла"
    return "файлов"


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
