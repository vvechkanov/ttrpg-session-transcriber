import QtQuick
import QtQuick.Layouts
import App.Theme
import "controls"

// One row in the sidebar nav list. Icon + label, with active / hover
// states matching the prototype:
//   active  → accentWash background, accentDeep text/icon, weight 600
//   hover   → cardAlt background
//   default → transparent
Rectangle {
    id: root

    property string itemKey: ""
    property string itemLabel: ""
    property string iconName: ""
    property bool active: false

    signal clicked()

    implicitHeight: 32
    radius: 7
    color: active
        ? Theme.accentWash
        : (hoverArea.containsMouse ? Theme.cardAlt : "transparent")
    // No Behavior on color — see controls/PrimaryButton for why a
    // 140 ms animation makes single-frame hover toggles flash.

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        spacing: 10

        SvgIcon {
            name: root.iconName
            size: 14
            strokeWidth: 1.7
            color: root.active ? Theme.accentDeep : Theme.ink3
        }

        Text {
            Layout.fillWidth: true
            text: root.itemLabel
            color: root.active ? Theme.accentDeep : Theme.ink2
            font.family: Theme.fontSans
            font.pixelSize: Theme.fontNav
            font.weight: root.active ? Font.DemiBold : Font.Medium
            elide: Text.ElideRight
        }
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
