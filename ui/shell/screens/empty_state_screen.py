"""EmptyStateScreen — initial screen before a session is opened (P0a, P2a).

Shown by :class:`ui.shell.app.MainWindow` when ``_session_dir is None``.
Replaces the previous behavior of rendering the full 4-block
:class:`SessionScreen` populated with a placeholder fixture, which
confused users: the big "Add source" tile in block 1 looked like the
entry point to load files, but it actually opened a parser picker
(``AddSourceDialog``) that required a session folder to already be open.

The empty state offers two obvious paths to a session folder:

    * drag-and-drop a folder onto the central drop zone;
    * click the "Выбрать папку…" primary button, which mirrors the
      existing ``File → Open session…`` menu (``Ctrl+O``).

P2a adds a compact "Недавние сессии" list below the drop zone so
returning users can reopen a previous session with a single click. The
list is purely presentational — the host (:class:`MainWindow`) owns
the persistent storage (:mod:`core.recent_sessions`) and pushes the
initial data in via the constructor's ``recent=`` kwarg or
:meth:`refresh_recent`.

Signals:
    pick_folder_requested: emitted when the primary button is clicked.
    folder_dropped(Path): emitted when a single directory is dropped
        onto the drop zone.
    recent_session_selected(Path): emitted when the user clicks the
        "открыть" button on a row in the "Недавние сессии" section.

Drag-and-drop rules (P0a):
    * Only directories accepted. A single file or multiple items shows a
      :class:`QMessageBox.warning` ("Перетащите папку сессии, а не
      отдельный файл") — single-file drops are handled by per-card flows
      in P3, not here.
    * While a valid drag-over is in progress the dashed border switches
      to ``theme.COLOR_ACCENT`` to signal the drop target is active.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.recent_sessions import RecentSession
from ui.shell import theme

#: Russian month abbreviations for the relative-time formatter. Order
#: matters — indexed by ``month - 1``.
_RU_MONTH_ABBR: tuple[str, ...] = tuple(
    "янв фев мар апр май июн июл авг сен окт ноя дек".split()
)


def _drop_zone_style(*, active: bool) -> str:
    """Return the dashed-border stylesheet for the drop zone frame.

    ``active`` switches the border color to the accent when a valid
    drag-over is in progress, giving the user a clear hit-test hint.
    """
    border_color = theme.COLOR_ACCENT if active else theme.COLOR_BORDER
    return f"""
        QFrame#emptyStateDropZone {{
            background-color: transparent;
            border: 2px dashed {border_color};
            border-radius: 16px;
        }}
    """


def _mime_single_dir(mime: QMimeData) -> Path | None:
    """Return the dropped path iff the payload is exactly one directory.

    Shared by the drop-zone's drag-enter / drag-move / drop event
    handlers and its testable :meth:`_DropZoneFrame.handle_mime_drop`
    entry point. ``None`` signals "not a valid folder drop" — the
    caller chooses whether to surface a warning or silently ignore.
    """
    if not mime.hasUrls():
        return None
    urls = mime.urls()
    if len(urls) != 1:
        return None
    path_str = urls[0].toLocalFile()
    if not path_str:
        return None
    path = Path(path_str)
    if not path.is_dir():
        return None
    return path


def _primary_button_style() -> str:
    """Accent pill button, styled to match ``SessionScreen._run_button``.

    Mirrors the idle-state branch of
    :meth:`ui.shell.screens.session_screen.SessionScreen._run_button_style`
    so the two primary CTAs feel visually consistent.
    """
    return f"""
        QPushButton {{
            color: {theme.COLOR_ACCENT_FG};
            background-color: {theme.COLOR_ACCENT};
            border: none;
            border-radius: {theme.RADIUS_CARD_PX}px;
            padding: 12px 28px;
            font-size: {theme.FONT_SIZE_H3_PX}px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {theme.COLOR_ACCENT_HOVER};
        }}
    """


def _ghost_button_style() -> str:
    """Muted link-style button for the per-row "открыть" action."""
    return f"""
        QPushButton {{
            color: {theme.COLOR_ACCENT};
            background-color: transparent;
            border: none;
            padding: 4px 8px;
            font-size: {theme.FONT_SIZE_SMALL_PX}px;
        }}
        QPushButton:hover {{
            color: {theme.COLOR_ACCENT_HOVER};
            text-decoration: underline;
        }}
    """


def _clear_link_style() -> str:
    """Muted link-style button for the "очистить" header action."""
    return f"""
        QPushButton {{
            color: {theme.COLOR_MUTED_FG};
            background-color: transparent;
            border: none;
            padding: 2px 6px;
            font-size: {theme.FONT_SIZE_SMALL_PX}px;
        }}
        QPushButton:hover {{
            color: {theme.COLOR_FOREGROUND};
            text-decoration: underline;
        }}
    """


def _format_relative_time(ts: float, *, now: datetime | None = None) -> str:
    """Format ``ts`` (unix seconds) as a short Russian relative-time label.

    Rules:
        * today (same calendar date) → ``"сегодня"``
        * yesterday → ``"вчера"``
        * within the last 7 days → ``"N дн. назад"``
        * otherwise → ``"DD MMM"`` with Russian month abbreviations.
    """
    now = now or datetime.now()
    when = datetime.fromtimestamp(ts)
    today = now.date()
    then = when.date()
    delta_days = (today - then).days
    if delta_days <= 0 and then == today:
        return "сегодня"
    if delta_days == 1:
        return "вчера"
    if 1 < delta_days <= 7:
        return f"{delta_days} дн. назад"
    month_abbr = _RU_MONTH_ABBR[then.month - 1]
    return f"{then.day} {month_abbr}"


class _DropZoneFrame(QFrame):
    """Inner drop-zone frame: handles drag events and emits signals.

    Kept as a nested class of :class:`EmptyStateScreen` rather than
    inlined on the screen itself so that the dashed border can be
    painted on the *inner* frame (the screen covers the whole central
    widget area — we want the dashed rectangle to be a visual card).
    """

    folder_dropped = Signal(Path)
    #: Raised when a drop payload is a file or multi-item — the screen
    #: surfaces a user-visible warning in response.
    invalid_drop = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyStateDropZone")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)
        self.setStyleSheet(_drop_zone_style(active=False))

    # ── Drag and drop ────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if _mime_single_dir(event.mimeData()) is not None:
            event.acceptProposedAction()
            self.setStyleSheet(_drop_zone_style(active=True))
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if _mime_single_dir(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self.setStyleSheet(_drop_zone_style(active=False))
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.setStyleSheet(_drop_zone_style(active=False))
        path = _mime_single_dir(event.mimeData())
        if path is None:
            self.invalid_drop.emit()
            event.ignore()
            return
        event.acceptProposedAction()
        self.folder_dropped.emit(path)

    def handle_mime_drop(self, mime: QMimeData) -> None:
        """Testable entry point for mime-data-driven drops.

        Synthesising a real :class:`QDropEvent` from Python is fragile
        (the event's ``mimeData()`` pointer is unwrapped as a generic
        ``QObject`` once the event is round-tripped through the C++
        layer, which makes calls like ``hasUrls()`` raise). Tests can
        call this method directly with a plain :class:`QMimeData`.
        """
        path = _mime_single_dir(mime)
        if path is None:
            self.invalid_drop.emit()
            return
        self.folder_dropped.emit(path)


class _RecentSessionRow(QFrame):
    """One row in the "Недавние сессии" list.

    Layout:
        📁  <basename>        <relative-time>        [открыть]

    The whole row is a :class:`QFrame` so it can carry a bottom-border
    separator and react to hover later without refactoring. Only the
    "открыть" button is clickable — keeps the hit-target unambiguous
    and avoids having to simulate row-wide hover states in QSS.
    """

    open_requested = Signal(Path)

    def __init__(
        self, session: RecentSession, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._session = session
        self.setObjectName("recentSessionRow")
        self.setStyleSheet(
            f"QFrame#recentSessionRow {{"
            f"  background-color: transparent;"
            f"  border: none;"
            f"  border-bottom: 1px solid {theme.COLOR_BORDER};"
            f"}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(theme.GAP_MEDIUM_PX)

        icon = QLabel("📁", self)
        icon.setStyleSheet(
            f"color: {theme.COLOR_ACCENT}; "
            f"font-size: {theme.FONT_SIZE_H3_PX}px; "
            "background: transparent;"
        )
        layout.addWidget(icon)

        title = QLabel(session.path.name or str(session.path), self)
        title.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_BODY_PX}px; "
            "background: transparent;"
        )
        layout.addWidget(title, stretch=1)

        when = QLabel(_format_relative_time(session.opened_at), self)
        when.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        when.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_SMALL_PX}px; "
            "background: transparent;"
        )
        layout.addWidget(when)

        open_btn = QPushButton("открыть", self)
        open_btn.setObjectName("recentOpenButton")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(_ghost_button_style())
        open_btn.clicked.connect(self._emit_open)
        layout.addWidget(open_btn)
        self._open_btn = open_btn

    @property
    def session_path(self) -> Path:
        return self._session.path

    def _emit_open(self) -> None:
        self.open_requested.emit(self._session.path)


class EmptyStateScreen(QWidget):
    """Landing screen shown before any session folder is opened.

    Layout:
        * Centered dashed drop zone (rounded corners, 16 px radius).
        * Big folder glyph at the top of the drop zone.
        * Big headline ("Перетащите папку сессии сюда").
        * Muted line "или".
        * Accent pill button "Выбрать папку…".
        * Muted footer hint: "Craig-бот → распакуйте .zip → перетащите
          папку".
        * (P2a) If ``recent`` is non-empty: a "Недавние сессии" card
          with one row per recent session.

    Signals:
        pick_folder_requested: primary button clicked.
        folder_dropped(Path): a valid directory was dropped. The host
            routes this to ``MainWindow._load_session``.
        recent_session_selected(Path): "открыть" clicked on a row in
            the recent sessions list.
    """

    pick_folder_requested = Signal()
    folder_dropped = Signal(Path)
    recent_session_selected = Signal(Path)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        recent: tuple[RecentSession, ...] = (),
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {theme.COLOR_BACKGROUND};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 48, 48, 48)
        outer.setSpacing(theme.GAP_LARGE_PX)

        outer.addStretch(1)

        self._drop_zone = _DropZoneFrame(parent=self)
        self._drop_zone.folder_dropped.connect(self.folder_dropped.emit)
        self._drop_zone.invalid_drop.connect(self._on_invalid_drop)

        zone_layout = QVBoxLayout(self._drop_zone)
        zone_layout.setContentsMargins(48, 56, 48, 56)
        zone_layout.setSpacing(theme.GAP_MEDIUM_PX)
        zone_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        folder_icon = QLabel("📁", self._drop_zone)
        folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_icon.setStyleSheet(
            f"color: {theme.COLOR_ACCENT}; "
            "font-size: 56px; "
            "background: transparent;"
        )
        zone_layout.addWidget(folder_icon, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("Перетащите папку сессии сюда", self._drop_zone)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_H1_PX}px; "
            "font-weight: 500; "
            "background: transparent;"
        )
        zone_layout.addWidget(title)

        or_label = QLabel("или", self._drop_zone)
        or_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        or_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_BODY_PX}px; "
            "background: transparent;"
        )
        zone_layout.addWidget(or_label)

        self._pick_button = QPushButton("Выбрать папку…", self._drop_zone)
        self._pick_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pick_button.setStyleSheet(_primary_button_style())
        self._pick_button.clicked.connect(self.pick_folder_requested.emit)
        zone_layout.addWidget(
            self._pick_button, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        outer.addWidget(self._drop_zone)

        footer = QLabel(
            "Craig-бот → распакуйте .zip → перетащите папку", self
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_SMALL_PX}px;"
        )
        outer.addWidget(footer)

        # ── Recent sessions card (P2a) ──────────────────────────────────
        self._recent_section = self._build_recent_section()
        outer.addWidget(self._recent_section)

        outer.addStretch(1)

        # Apply initial data now that every widget is in place.
        self.refresh_recent(recent)

    # ── Recent sessions (P2a) ────────────────────────────────────────

    def _build_recent_section(self) -> QWidget:
        """Build the "Недавние сессии" container (header + rows area)."""
        section = QWidget(self)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(theme.GAP_SMALL_PX)

        header_row = QWidget(section)
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(theme.GAP_SMALL_PX)

        header_label = QLabel("Недавние сессии", header_row)
        header_label.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_H3_PX}px; "
            "font-weight: 500; "
            "background: transparent;"
        )
        header_layout.addWidget(header_label, stretch=1)

        self._clear_button = QPushButton("очистить", header_row)
        self._clear_button.setObjectName("recentClearButton")
        self._clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_button.setStyleSheet(_clear_link_style())
        self._clear_button.clicked.connect(self._on_clear_clicked)
        header_layout.addWidget(self._clear_button)

        section_layout.addWidget(header_row)

        # Container that will hold the row widgets. We rebuild its
        # contents on every refresh_recent() call.
        self._rows_container = QWidget(section)
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        section_layout.addWidget(self._rows_container)

        return section

    def refresh_recent(self, sessions: tuple[RecentSession, ...]) -> None:
        """Rebuild the recent-sessions rows from ``sessions``.

        Hides the whole section (header + rows) when ``sessions`` is
        empty — we don't want a lonely "Недавние сессии" header with
        nothing under it on first run.
        """
        # Tear down any previous rows. ``takeAt(0)`` removes items in
        # order; ``setParent(None)`` detaches the widget so Qt will
        # garbage-collect it.
        while self._rows_layout.count() > 0:
            item = self._rows_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if not sessions:
            self._recent_section.setVisible(False)
            return

        self._recent_section.setVisible(True)
        for s in sessions:
            row = _RecentSessionRow(s, parent=self._rows_container)
            row.open_requested.connect(self.recent_session_selected.emit)
            self._rows_layout.addWidget(row)

    def _on_clear_clicked(self) -> None:
        """Clear the persisted list and hide the section."""
        # Imported lazily so a test that monkeypatches
        # ``ui.shell.screens.empty_state_screen.clear_recent`` still
        # overrides the callable actually invoked here.
        from core import recent_sessions

        recent_sessions.clear_recent()
        self.refresh_recent(())

    # ── Slots ────────────────────────────────────────────────────────

    def _on_invalid_drop(self) -> None:
        """Surface a warning when the user drops a file instead of a folder."""
        QMessageBox.warning(
            self,
            "Неверный формат",
            "Перетащите папку сессии, а не отдельный файл.",
        )
