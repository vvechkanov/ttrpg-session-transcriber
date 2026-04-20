import QtQuick
import QtQuick.Layouts
import App.Theme

// Checkbox + label, row-shaped. Toggles on click anywhere in the row.
// Used for settings-page toggles ("Показывать подсказки…"), drawer
// switches, etc. The earlier inline version in ModelDetailsDrawer
// remains there until the drawer's full wiring phase — shared control
// is used going forward.
RowLayout {
    id: root

    property string text: ""
    property bool checked: false

    Layout.fillWidth: true
    spacing: 8

    Rectangle {
        Layout.preferredWidth: 14
        Layout.preferredHeight: 14
        radius: 3
        border.width: 1
        border.color: root.checked ? Theme.accent : Theme.border
        color: root.checked ? Theme.accent : Theme.card

        SvgIcon {
            anchors.centerIn: parent
            visible: root.checked
            name: "check"
            size: 11
            color: Theme.accentFg
            strokeWidth: 2.2
        }
    }

    Text {
        Layout.fillWidth: true
        text: root.text
        color: Theme.ink2
        font.family: Theme.fontSans
        font.pixelSize: 12
    }

    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: root.checked = !root.checked }
}
