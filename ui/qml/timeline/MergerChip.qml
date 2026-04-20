import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Clickable pill showing the current merger preset. Idle phase renders
// the neutral variant (card bg, inkFaint chev). `active` would flip
// it to accentWash once the merge phase is wired.
Rectangle {
    id: root

    property string caption: "ScriptMerger · gap ≤ 1.0с"
    property bool active: false
    signal clicked()

    implicitHeight: 38
    implicitWidth: row.implicitWidth + 28
    radius: Theme.radiusSm + 2
    color: active
        ? Theme.accentWash
        : (hoverMa.containsMouse ? Theme.cardAlt : Theme.card)
    border.width: 1
    border.color: active ? Theme.accentSoft : Theme.border

    Behavior on color { ColorAnimation { duration: Theme.animFast } }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 10
        spacing: 10

        Rectangle {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            radius: 999
            color: root.active ? Theme.accent : Theme.cardAlt

            SvgIcon {
                anchors.centerIn: parent
                name: "sparkle"; size: 12
                color: root.active ? Theme.accentFg : Theme.ink3
                strokeWidth: 1.8
            }
        }

        Text {
            text: root.caption
            color: root.active ? Theme.accentDeep : Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: 12
            font.weight: Font.DemiBold
            font.letterSpacing: -0.05
        }

        SvgIcon {
            name: "chevRight"; size: 13
            color: root.active ? Theme.accentDeep : Theme.ink4
            strokeWidth: 1.7
        }
    }

    MouseArea {
        id: hoverMa
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
