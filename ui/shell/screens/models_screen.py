"""Models management screen (P1b).

Modal dialog listing every registered :class:`core.backend_installers.BackendId`
with its current install state, occupied disk size (or approximate download
size if not installed), and Install/Uninstall actions. Reuses the existing
:func:`ui.shell.install_wizard.ensure_backend_installed` flow for installs,
and goes through :func:`core.backend_installers.uninstall_backend` for the
reverse path. Exposes a single public class :class:`ModelsScreen`.

Accessible from the main menu — ``Модели → Управление моделями…``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from core.backend_installers import (
    BACKENDS,
    BackendId,
    BackendInfo,
    installed_size_bytes,
    is_backend_installed,
    uninstall_backend,
)
from ui.shell import theme
from ui.shell.install_wizard import ensure_backend_installed


_MB = 1024 * 1024
_GB = 1024 * 1024 * 1024


def _format_size(num_bytes: int) -> str:
    """Format a byte count as ``"N MB"`` or ``"N.N GB"``.

    Rules:
        * Values below 1 GB are shown as whole MB (integer division).
        * Values >= 1 GB are shown in GB with one decimal.
        * Zero returns ``"0 MB"``.
    """
    if num_bytes <= 0:
        return "0 MB"
    if num_bytes < _GB:
        mb = num_bytes // _MB
        return f"{mb} MB"
    gb = num_bytes / _GB
    return f"{gb:.1f} GB"


class _ModelRow(QFrame):
    """One card row in :class:`ModelsScreen`.

    Presentational only; the hosting screen owns install/uninstall logic
    and calls :meth:`refresh` after state changes.
    """

    def __init__(
        self,
        info: BackendInfo,
        *,
        on_install: "callable[[BackendId], None]",
        on_uninstall: "callable[[BackendId], None]",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._info = info
        self._on_install = on_install
        self._on_uninstall = on_uninstall

        self.setObjectName("modelRow")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"QFrame#modelRow {{"
            f" background-color: {theme.COLOR_CARD};"
            f" border: 1px solid {theme.COLOR_BORDER};"
            f" border-radius: {theme.RADIUS_CARD_PX}px;"
            f" }}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(theme.SHADOW_CARD_BLUR_RADIUS)
        shadow.setOffset(0, theme.SHADOW_CARD_OFFSET_Y)
        shadow.setColor(QColor(*theme.SHADOW_CARD_RGBA))
        self.setGraphicsEffect(shadow)

        root = QHBoxLayout(self)
        root.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_COMPACT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_COMPACT_PX,
        )
        root.setSpacing(theme.GAP_MEDIUM_PX)

        # Left column — icon + title/subtitle
        icon = QLabel("\U0001F399", self)  # microphone glyph
        icon.setStyleSheet(
            f"font-size: {theme.FONT_SIZE_H2_PX}px;"
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        root.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(4)

        title_label = QLabel(info.title, self)
        title_label.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND};"
            f" font-size: {theme.FONT_SIZE_H3_PX}px;"
            f" font-weight: 500;"
        )
        text_col.addWidget(title_label)

        subtitle_label = QLabel(info.description, self)
        subtitle_label.setObjectName("subtitleLabel")
        subtitle_label.setWordWrap(True)
        subtitle_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG};"
            f" font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        text_col.addWidget(subtitle_label)
        root.addLayout(text_col, stretch=1)

        # Right column — status chip, size, button (stacked vertically so
        # long titles don't push them off-screen)
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(theme.GAP_SMALL_PX)
        right_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self._status_chip = QLabel(self)
        self._status_chip.setObjectName("statusChip")
        self._status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_col.addWidget(self._status_chip, alignment=Qt.AlignmentFlag.AlignRight)

        self._size_label = QLabel(self)
        self._size_label.setObjectName("sizeLabel")
        self._size_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._size_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG};"
            f" font-size: {theme.FONT_SIZE_SMALL_PX}px;"
        )
        right_col.addWidget(self._size_label, alignment=Qt.AlignmentFlag.AlignRight)

        self._action_button = QPushButton(self)
        self._action_button.setObjectName("actionButton")
        self._action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_button.clicked.connect(self._on_action_clicked)
        right_col.addWidget(
            self._action_button, alignment=Qt.AlignmentFlag.AlignRight
        )

        root.addLayout(right_col)

        # Populate state-dependent widgets
        self.refresh()

    # ── Public ──────────────────────────────────────────────────────────

    @property
    def backend_id(self) -> BackendId:
        """Backend this row represents."""
        return self._info.id

    def is_installed(self) -> bool:
        """Return the last-refreshed install state for this backend."""
        return self._installed

    def refresh(self) -> None:
        """Re-query install state and update chip/size/button."""
        self._installed = is_backend_installed(self._info.id)
        if self._installed:
            size_bytes = installed_size_bytes(self._info.id)
            self._size_label.setText(_format_size(size_bytes))
            self._status_chip.setText("\u2713 установлена")
            self._status_chip.setStyleSheet(self._chip_style(installed=True))
            self._action_button.setText("Удалить")
            self._action_button.setStyleSheet(self._button_style(destructive=True))
        else:
            size_bytes = self._info.approx_download_bytes
            self._size_label.setText(f"~{_format_size(size_bytes)}")
            self._status_chip.setText("\u25CB не установлена")
            self._status_chip.setStyleSheet(self._chip_style(installed=False))
            self._action_button.setText("Установить")
            self._action_button.setStyleSheet(self._button_style(destructive=False))

    # ── Private ─────────────────────────────────────────────────────────

    def _on_action_clicked(self) -> None:
        if self._installed:
            self._on_uninstall(self._info.id)
        else:
            self._on_install(self._info.id)

    @staticmethod
    def _chip_style(*, installed: bool) -> str:
        if installed:
            bg = "rgba(90, 138, 62, 0.12)"
            fg = theme.COLOR_SUCCESS
        else:
            bg = theme.COLOR_SECONDARY
            fg = theme.COLOR_MUTED_FG
        return (
            f"QLabel#statusChip {{"
            f" color: {fg};"
            f" background-color: {bg};"
            f" border-radius: {theme.RADIUS_CHIP_PX}px;"
            f" padding: 4px 10px;"
            f" font-size: {theme.FONT_SIZE_MICRO_PX}px;"
            f" }}"
        )

    @staticmethod
    def _button_style(*, destructive: bool) -> str:
        if destructive:
            return (
                f"QPushButton#actionButton {{"
                f" color: #B93834;"
                f" background-color: transparent;"
                f" border: 1px solid rgba(185, 56, 52, 0.35);"
                f" padding: 6px 14px;"
                f" border-radius: {theme.RADIUS_BUTTON_PX}px;"
                f" font-size: {theme.FONT_SIZE_BODY_PX}px;"
                f" }}"
                f"QPushButton#actionButton:hover {{"
                f" background-color: rgba(185, 56, 52, 0.08);"
                f" }}"
            )
        return (
            f"QPushButton#actionButton {{"
            f" color: {theme.COLOR_ACCENT_FG};"
            f" background-color: {theme.COLOR_ACCENT};"
            f" border: none;"
            f" padding: 6px 14px;"
            f" border-radius: {theme.RADIUS_BUTTON_PX}px;"
            f" font-size: {theme.FONT_SIZE_BODY_PX}px;"
            f" }}"
            f"QPushButton#actionButton:hover {{"
            f" background-color: {theme.COLOR_ACCENT_HOVER};"
            f" }}"
        )


class ModelsScreen(QDialog):
    """Modal «Управление моделями» screen.

    Lists every :class:`BackendId` registered in
    :data:`core.backend_installers.BACKENDS` and lets the user install
    or uninstall each one. After install/uninstall the screen refreshes
    all rows and the total-on-disk summary.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Управление моделями")
        self.setModal(True)
        self.resize(680, 480)
        self.setStyleSheet(
            f"QDialog {{ background-color: {theme.COLOR_BACKGROUND}; }}"
        )

        self._rows: list[_ModelRow] = []
        self._total_label: QLabel | None = None

        self._build_ui()

    # ── Public ──────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Re-query every row and update the total-on-disk summary."""
        for row in self._rows:
            row.refresh()
        self._update_total()

    # ── UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
            theme.PAD_CONTENT_PX,
        )
        root.setSpacing(theme.GAP_MEDIUM_PX)

        header = QLabel("Управление моделями", self)
        header.setStyleSheet(
            f"color: {theme.COLOR_FOREGROUND};"
            f" font-size: {theme.FONT_SIZE_H1_PX}px;"
            f" font-weight: 600;"
        )
        root.addWidget(header)

        # Scrollable list of rows (future-proof: BACKENDS will grow).
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        rows_host = QWidget(scroll)
        rows_host.setStyleSheet("background: transparent;")
        rows_layout = QVBoxLayout(rows_host)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(theme.GAP_MEDIUM_PX)

        for info in BACKENDS.values():
            row = _ModelRow(
                info,
                on_install=self._handle_install,
                on_uninstall=self._handle_uninstall,
                parent=rows_host,
            )
            self._rows.append(row)
            rows_layout.addWidget(row)

        rows_layout.addStretch(1)
        scroll.setWidget(rows_host)
        root.addWidget(scroll, stretch=1)

        # Total on disk summary
        self._total_label = QLabel(self)
        self._total_label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG};"
            f" font-size: {theme.FONT_SIZE_SMALL_PX}px;"
        )
        root.addWidget(self._total_label)
        self._update_total()

        # Close button
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, parent=self
        )
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        # Close button goes through the ButtonRole.RejectRole — wire it
        # explicitly so clicking closes the dialog.
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        root.addWidget(buttons)

    def _update_total(self) -> None:
        """Recompute and render the "Всего на диске" label."""
        if self._total_label is None:
            return
        total = 0
        for row in self._rows:
            if row.is_installed():
                try:
                    total += installed_size_bytes(row.backend_id)
                except Exception:  # noqa: BLE001 — defensive; show 0
                    continue
        self._total_label.setText(f"Всего на диске: {_format_size(total)}")

    # ── Actions ─────────────────────────────────────────────────────────

    def _handle_install(self, backend_id: BackendId) -> None:
        """Route an install click through the shared wizard, then refresh."""
        try:
            ensure_backend_installed(backend_id, parent=self)
        except Exception as exc:  # noqa: BLE001 — UI boundary
            QMessageBox.critical(
                self,
                "Ошибка установки модели",
                f"Не удалось установить «{BACKENDS[backend_id].title}»:\n\n{exc}",
            )
        self.refresh()

    def _handle_uninstall(self, backend_id: BackendId) -> None:
        """Confirm and delete backend files; refresh rows on success."""
        info = BACKENDS[backend_id]
        try:
            size_bytes = installed_size_bytes(backend_id)
        except Exception:  # noqa: BLE001 — defensive
            size_bytes = 0
        size_text = _format_size(size_bytes)
        answer = QMessageBox.question(
            self,
            "Удаление модели",
            (
                f"Удалить модель «{info.title}»? "
                f"Файлы бэкенда будут стёрты с диска ({size_text})."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            uninstall_backend(backend_id)
        except Exception as exc:  # noqa: BLE001 — UI boundary
            QMessageBox.critical(
                self,
                "Ошибка удаления модели",
                f"Не удалось удалить «{info.title}»:\n\n{exc}",
            )
        self.refresh()
