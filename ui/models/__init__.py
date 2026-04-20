"""Qt/QML view-models.

These classes expose application state to QML via ``Q_PROPERTY`` and
``QAbstractListModel``. They live in the UI layer and may depend on
``core/`` but not the other way around.

The new QML shell (``ui/qml/`` + ``ui.app_qml``) uses these models.
The legacy QWidgets shell in ``ui/shell/`` is independent.
"""

from ui.models.app_model import AppModel
from ui.models.app_preferences import AppPreferences
from ui.models.model_registry import ModelRegistry
from ui.models.session_mock import (
    SEG1_END_PCT,
    SEG_SPLIT_MIN,
    TOTAL_MIN,
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
    "TOTAL_MIN",
    "SEG_SPLIT_MIN",
    "SEG1_END_PCT",
]
