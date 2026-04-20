"""First-run onboarding overlay (P2b).

Semi-transparent dim layer sized to the parent's full area, with a
centered welcome card pointing users at the drop zone. Dismissing the
card persists the "seen" flag via :func:`core.onboarding_state.mark_onboarded`
so it never reappears.

The overlay is a sibling child of :class:`MainWindow.centralWidget`,
not part of any layout — we manually reposition it on parent resize
events so it always covers the whole window. This keeps the
empty-state screen layout untouched (drop zone stays centered under
the overlay) and avoids a full-window QStackedWidget detour for a
one-shot welcome.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.shell import theme


def _card_style() -> str:
    """White rounded card in the middle of the dim layer."""
    return f"""
        QFrame#onboardingCard {{
            background-color: {theme.COLOR_CARD};
            border-radius: 16px;
            padding: 8px;
        }}
    """


def _primary_button_style() -> str:
    """Accent pill button for the "Понятно, начнём" CTA."""
    return f"""
        QPushButton {{
            color: {theme.COLOR_ACCENT_FG};
            background-color: {theme.COLOR_ACCENT};
            border: none;
            border-radius: {theme.RADIUS_CARD_PX}px;
            padding: 10px 24px;
            font-size: {theme.FONT_SIZE_H3_PX}px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {theme.COLOR_ACCENT_HOVER};
        }}
    """


class OnboardingOverlay(QWidget):
    """Dim overlay with a welcome card — shown once, then dismissed forever.

    The overlay covers the entire parent widget; the card sits
    centered on top of it. Clicking the dismiss button calls
    :func:`core.onboarding_state.mark_onboarded` and hides the overlay.

    Signals:
        dismissed: emitted after the dismiss button is clicked and the
            flag has been persisted. The host can react (e.g. remove
            the overlay from memory) but no reaction is required —
            the overlay hides itself regardless.
    """

    dismissed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("onboardingOverlay")
        # Opaque-to-mouse so clicks don't fall through to the screen
        # underneath. Backdrop style comes from ``theme``; the parent
        # owns the geometry via resizeEvent.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget#onboardingOverlay {"
            "  background-color: rgba(0, 0, 0, 140);"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame(self)
        card.setObjectName("onboardingCard")
        card.setFrameShape(QFrame.Shape.NoFrame)
        card.setStyleSheet(_card_style())
        card.setMaximumWidth(560)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
        )
        card_layout.setSpacing(theme.GAP_MEDIUM_PX)

        title = QLabel("\U0001F44B Добро пожаловать!", card)
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND}; "
            f"font-size: {theme.FONT_SIZE_H1_PX}px; "
            "font-weight: 500; "
            "background: transparent;"
        )
        card_layout.addWidget(title)

        body = QLabel(
            "Чтобы начать, перетащите папку с записью сессии на окно "
            "или нажмите «Выбрать папку…».",
            card,
        )
        body.setWordWrap(True)
        body.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_BODY_PX}px; "
            "background: transparent;"
        )
        card_layout.addWidget(body)

        self._dismiss_button = QPushButton("Понятно, начнём", card)
        self._dismiss_button.setObjectName("onboardingDismissButton")
        self._dismiss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_button.setStyleSheet(_primary_button_style())
        self._dismiss_button.clicked.connect(self._on_dismiss_clicked)
        card_layout.addWidget(
            self._dismiss_button,
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        layout.addWidget(card)

        # Size to the parent immediately so show() places us correctly.
        self._resize_to_parent()

        # Watch the parent so the overlay always fills its client area.
        parent.installEventFilter(self)

    # ── Geometry tracking ────────────────────────────────────────────

    def eventFilter(self, obj: object, event: QEvent) -> bool:  # noqa: N802
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self._resize_to_parent()
        return super().eventFilter(obj, event)

    def _resize_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(0, 0, parent.width(), parent.height())

    # ── Dismiss ──────────────────────────────────────────────────────

    def _on_dismiss_clicked(self) -> None:
        """Persist the onboarded flag, hide the overlay, emit signal."""
        # Lazy import so tests can monkeypatch
        # ``core.onboarding_state.mark_onboarded`` and still hit the
        # patched callable.
        from core import onboarding_state

        onboarding_state.mark_onboarded()
        self.hide()
        self.dismissed.emit()
