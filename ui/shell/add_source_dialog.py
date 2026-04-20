"""Add-source picker for the Session Transcriber shell.

When the user clicks ``+ добавить источник`` on the Session screen we
open :class:`AddSourceDialog`, a small modal that lists every parser
the app knows about. The user picks one, and the dialog reports the
choice back via :attr:`selected_key`.

For speech parsers (``gigaam`` / ``faster-whisper``) the picker shows
whether the backing ASR bundle is already installed — this way the
user knows up-front whether clicking the item will trigger a download.
Chat parsers have no heavyweight dependency and are always listed as
ready to add.

The dialog is **presentation only**. It does not perform any install
itself — the host (``ui.shell.app``) takes ``selected_key`` and routes
it through :func:`ui.shell.install_wizard.ensure_backend_installed`
before attaching the new source card to the session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.backend_installers import (
    BackendId,
    BACKENDS,
    is_backend_installed,
)


#: Distinct UI keys for every parser the dialog offers. Kept as plain
#: strings so the host does not need to depend on any ``sources/``
#: class imports directly.
KEY_GIGAAM = "gigaam"
KEY_FASTER_WHISPER = "faster-whisper"
KEY_FVTT_CHAT = "fvtt-chat"


@dataclass(frozen=True)
class ParserOption:
    """Single entry in the add-source picker.

    Attributes:
        key: stable identifier the host uses to decide which module to
            construct.
        title: user-visible parser name.
        subtitle: one-line summary (backend / format / size).
        backend_id: ASR bundle that must be installed before the parser
            can run, or ``None`` when no install is required.
    """

    key: str
    title: str
    subtitle: str
    backend_id: Optional[BackendId] = None


def build_parser_options() -> list[ParserOption]:
    """Return the canonical list of parsers offered in the dialog.

    Kept as a function (not a const) so the subtitle can inline the
    current approximate download size straight from
    :data:`core.backend_installers.BACKENDS` without duplicating it
    here. When a new backend is registered in
    ``core.backend_installers``, adding an entry here makes it
    available in the UI picker.
    """
    gigaam_info = BACKENDS[BackendId.GIGAAM_RNNT_FP32]
    fw_info = BACKENDS[BackendId.FASTER_WHISPER_LARGE_V3_RU]

    def _size_mb(info) -> int:
        return info.approx_download_bytes // 1_000_000

    return [
        ParserOption(
            key=KEY_GIGAAM,
            title="Аудио · GigaAM-v3 RNNT",
            subtitle=f"Русский ASR от Сбера · ~{_size_mb(gigaam_info)} MB",
            backend_id=BackendId.GIGAAM_RNNT_FP32,
        ),
        ParserOption(
            key=KEY_FASTER_WHISPER,
            title="Аудио · faster-whisper large-v3 (ru)",
            subtitle=f"Файнтюн Whisper от bzikst · ~{_size_mb(fw_info)} MB",
            backend_id=BackendId.FASTER_WHISPER_LARGE_V3_RU,
        ),
        ParserOption(
            key=KEY_FVTT_CHAT,
            title="Foundry VTT — чат-лог",
            subtitle="Парсер чата Foundry VTT · без моделей",
            backend_id=None,
        ),
    ]


class AddSourceDialog(QDialog):
    """Modal that lets the user pick a parser to add to the session.

    Usage::

        dlg = AddSourceDialog(parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_key:
            key = dlg.selected_key
            # route through ensure_backend_installed() if needed
            ...

    The dialog never installs anything. It just reports which option
    the user picked; the host decides whether an install wizard needs
    to run before the card is attached.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        options: list[ParserOption] | None = None,
    ) -> None:
        super().__init__(parent)
        self._options = options if options is not None else build_parser_options()
        self._selected_key: Optional[str] = None

        self.setWindowTitle("Добавить парсер")
        self.setModal(True)
        self.resize(520, 360)

        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        heading = QLabel("Выберите парсер для сессии", self)
        heading.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(heading)

        hint = QLabel(
            "Если модель ещё не установлена, мы предложим скачать её "
            "после выбора.",
            self,
        )
        hint.setStyleSheet("color: #6c7086; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._list = QListWidget(self)
        for option in self._options:
            self._list.addItem(self._make_item(option))
        self._list.itemDoubleClicked.connect(lambda _item: self._accept())
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        layout.addWidget(self._list, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_item(self, option: ParserOption) -> QListWidgetItem:
        """Render a single option into a :class:`QListWidgetItem`.

        Each item carries the :class:`ParserOption` via ``UserRole`` so
        ``_accept`` can recover the user's choice without depending on
        list index stability.
        """
        if option.backend_id is None:
            status = "готов"
        elif is_backend_installed(option.backend_id):
            status = "установлен"
        else:
            status = "потребуется установка"

        text = f"{option.title}\n{option.subtitle} · {status}"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, option)
        return item

    # ── Selection ────────────────────────────────────────────────────

    @property
    def selected_key(self) -> Optional[str]:
        """Key of the picked :class:`ParserOption`, or ``None`` on cancel."""
        return self._selected_key

    def _accept(self) -> None:
        item = self._list.currentItem()
        if item is None:
            self.reject()
            return
        option = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(option, ParserOption):
            self.reject()
            return
        self._selected_key = option.key
        self.accept()
