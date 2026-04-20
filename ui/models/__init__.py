"""Qt/QML view-models.

These classes expose application state to QML via ``Q_PROPERTY`` and
``QAbstractListModel``. They live in the UI layer and may depend on
``core/`` but not the other way around. Consumed from
``ui/qml/`` via context properties set in ``ui.app_qml``.
"""

from ui.models.app_model import AppModel
from ui.models.app_preferences import AppPreferences
from ui.models.model_registry import ModelRegistry
from ui.models.session import (
    SessionMeta,
    SourceListModel,
    TrackListModel,
)

__all__ = [
    "AppModel",
    "AppPreferences",
    "ModelRegistry",
    "SessionMeta",
    "SourceListModel",
    "TrackListModel",
]
