"""List model for ASR models shown on the Models screen.

For this UI slice the registry is populated with the same six mock
rows the HTML prototype ships with. Real discovery (scanning the
configured models folder, reading metadata from :mod:`core.backend_installers`,
resolving active vs. installed) is introduced later — the Q_PROPERTY
and role-name shape here is the contract QML will keep binding to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Slot


@dataclass
class ModelEntry:
    name: str
    vendor: str
    size: str
    lang: str
    accuracy: int   # 0..100
    speed: str      # free-form Russian label: "очень быстро", "быстро", "средне", "медленно"
    installed: bool
    active: bool


_PROTOTYPE_ROWS: list[ModelEntry] = [
    ModelEntry(name="GigaAM-v3 RNNT (int8)", vendor="Salute",
               size="420 MB", lang="RU", accuracy=98,
               speed="быстро", installed=True, active=True),
    ModelEntry(name="GigaAM-v3 RNNT (fp32)", vendor="Salute",
               size="820 MB", lang="RU", accuracy=99,
               speed="средне", installed=True, active=False),
    ModelEntry(name="faster-whisper large-v3", vendor="OpenAI + CTranslate2",
               size="3.1 GB", lang="RU/EN/мульти.", accuracy=97,
               speed="медленно", installed=True, active=False),
    ModelEntry(name="faster-whisper medium", vendor="OpenAI + CTranslate2",
               size="1.5 GB", lang="RU/EN", accuracy=93,
               speed="быстро", installed=False, active=False),
    ModelEntry(name="faster-whisper small", vendor="OpenAI + CTranslate2",
               size="480 MB", lang="RU/EN", accuracy=87,
               speed="очень быстро", installed=False, active=False),
    ModelEntry(name="Vosk ru-0.42", vendor="Alpha Cephei",
               size="1.7 GB", lang="RU", accuracy=85,
               speed="средне", installed=False, active=False),
]


class ModelRegistry(QAbstractListModel):
    NameRole      = Qt.ItemDataRole.UserRole + 1
    VendorRole    = Qt.ItemDataRole.UserRole + 2
    SizeRole      = Qt.ItemDataRole.UserRole + 3
    LangRole      = Qt.ItemDataRole.UserRole + 4
    AccuracyRole  = Qt.ItemDataRole.UserRole + 5
    SpeedRole     = Qt.ItemDataRole.UserRole + 6
    InstalledRole = Qt.ItemDataRole.UserRole + 7
    ActiveRole    = Qt.ItemDataRole.UserRole + 8

    _ROLES: dict[int, bytes] = {
        NameRole:      b"name",
        VendorRole:    b"vendor",
        SizeRole:      b"size",
        LangRole:      b"lang",
        AccuracyRole:  b"accuracy",
        SpeedRole:     b"speed",
        InstalledRole: b"installed",
        ActiveRole:    b"active",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        # Copy so rowCount/data mutations never touch the module-level list.
        self._rows: list[ModelEntry] = list(_PROTOTYPE_ROWS)

    # ── QAbstractListModel overrides ──────────────────────────────────
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        match role:
            case ModelRegistry.NameRole:      return row.name
            case ModelRegistry.VendorRole:    return row.vendor
            case ModelRegistry.SizeRole:      return row.size
            case ModelRegistry.LangRole:      return row.lang
            case ModelRegistry.AccuracyRole:  return row.accuracy
            case ModelRegistry.SpeedRole:     return row.speed
            case ModelRegistry.InstalledRole: return row.installed
            case ModelRegistry.ActiveRole:    return row.active
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name) for role, name in self._ROLES.items()}

    # ── Helpers used by QML via context-property ──────────────────────
    @Slot(int, result="QVariant")
    def entryAt(self, row: int) -> dict[str, Any] | None:
        """Snapshot a row as a plain dict — convenient for the drawer.

        Returning a ``QVariantMap``-shaped ``dict`` lets QML read fields
        like ``model.name``, ``model.vendor``… without subscripting.
        """

        if not (0 <= row < len(self._rows)):
            return None
        e = self._rows[row]
        return {
            "name":      e.name,
            "vendor":    e.vendor,
            "size":      e.size,
            "lang":      e.lang,
            "accuracy":  e.accuracy,
            "speed":     e.speed,
            "installed": e.installed,
            "active":    e.active,
        }
