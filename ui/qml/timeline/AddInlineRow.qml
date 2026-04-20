import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Compact "+ добавить …" row used below the sources panel and the
// tracks panel. Two-column layout (220px gutter + fill) matching the
// panels above it, so the left divider aligns.
Item {
    id: root

    property int gutterWidth: 220
    property string label: "добавить"
    signal activated()

    implicitHeight: 28

    // Top dashed separator.
    Canvas {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 1

        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, 1)
            ctx.beginPath()
            ctx.strokeStyle = Theme.borderSoft
            ctx.lineWidth = 1
            ctx.setLineDash([3, 3])
            ctx.moveTo(0, 0.5)
            ctx.lineTo(width, 0.5)
            ctx.stroke()
        }
    }

    // Clickable left gutter.
    Rectangle {
        id: gutter
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.topMargin: 1
        width: root.gutterWidth
        height: parent.height - 1
        color: hoverMa.containsMouse ? Theme.cardAlt : "transparent"

        Behavior on color { ColorAnimation { duration: Theme.animFast } }

        Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 1
            color: Theme.borderSoft
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 6

            SvgIcon {
                name: "plus"; size: 11
                color: Theme.ink3
                strokeWidth: 1.7
            }

            Text {
                Layout.fillWidth: true
                text: root.label
                color: Theme.ink3
                font.family: Theme.fontSans
                font.pixelSize: 11
            }
        }

        MouseArea {
            id: hoverMa
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.activated()
        }
    }
}
