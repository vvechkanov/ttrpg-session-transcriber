"""Qt/QML view-models.

These classes expose application state to QML via ``Q_PROPERTY`` and
``QAbstractListModel``. They live in the UI layer and may depend on
``core/`` but not the other way around.

The new QML shell (``ui/qml/`` + ``ui.app_qml``) uses these models.
The legacy QWidgets shell in ``ui/shell/`` is independent.
"""

from ui.models.app_model import AppModel

__all__ = ["AppModel"]
