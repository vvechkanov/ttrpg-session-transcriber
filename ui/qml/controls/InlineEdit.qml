import QtQuick
import QtQuick.Controls.Basic
import App.Theme

// Click-to-edit text label.
//
// Defaults to a plain Text. On click, when `locked` is false, it
// switches to a focused TextField with an accent border. Enter or
// focus-loss commit; Escape reverts.
//
// Usage:
//     InlineEdit {
//         text: modelData.name
//         locked: appModel.phase !== "idle"
//         onCommitted: (value) => tracksModel.setPlayerName(row, value)
//     }
//
// The control stays fixed-width on its container — no jumping between
// Text and TextField geometry.
Item {
    id: root

    property string text: ""
    property bool locked: false
    property alias font: label.font
    property color color: Theme.ink
    property int minWidth: 60

    signal committed(string value)

    implicitHeight: Math.max(
        label.implicitHeight,
        editor.implicitHeight
    )
    implicitWidth: Math.max(minWidth, Math.min(
        editor.visible ? editor.contentWidth + 16 : label.implicitWidth,
        220
    ))

    // Tracked separately so Esc can revert to the pre-edit value
    // without losing the caller's binding source.
    property string _pending: text

    // ── Display mode ──────────────────────────────────────────────
    Text {
        id: label
        anchors.verticalCenter: parent.verticalCenter
        visible: !editor.visible
        text: root.text
        color: root.color
        font.family: Theme.fontSans
        elide: Text.ElideRight
        width: parent.width
    }

    // Click target covers the label. Disabled when `locked`.
    MouseArea {
        anchors.fill: parent
        visible: !editor.visible && !root.locked
        cursorShape: Qt.IBeamCursor
        onClicked: {
            root._pending = root.text
            editor.visible = true
            editor.forceActiveFocus()
            editor.selectAll()
        }
    }

    // ── Edit mode ─────────────────────────────────────────────────
    TextField {
        id: editor
        anchors.verticalCenter: parent.verticalCenter
        visible: false
        width: root.width

        text: root._pending
        color: root.color
        selectionColor: Theme.accentSoft
        selectedTextColor: Theme.ink
        font: label.font

        leftPadding: 5
        rightPadding: 5
        topPadding: 1
        bottomPadding: 1

        background: Rectangle {
            radius: 4
            color: Theme.card
            border.width: 1
            border.color: Theme.accent
        }

        onTextChanged: root._pending = text
        onAccepted: _commit()       // Enter
        onActiveFocusChanged: {
            if (!activeFocus && visible) {
                _commit()            // focus-loss commits
            }
        }
        Keys.onEscapePressed: {
            root._pending = root.text
            editor.visible = false
        }

        function _commit() {
            if (_pending !== root.text) {
                root.committed(_pending)
            }
            visible = false
        }
    }
}
