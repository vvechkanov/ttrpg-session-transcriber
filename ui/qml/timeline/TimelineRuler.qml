import QtQuick
import QtQuick.Shapes
import App.Theme
import "../controls"

// Ruler strip: 30-minute tick marks (major every hour, minor every
// half-hour), mono labels at majors, and a scissors-badged dashed line
// at the Craig segment split.
//
// Positions are computed from `totalMinutes` and `segmentSplitPct` so
// the widget is reusable for any session length.
Item {
    id: root

    property int totalMinutes: 227
    property real segmentSplitPct: 66.0

    implicitHeight: 22

    // Thin bottom separator.
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.borderSoft
    }

    // Tick marks
    Repeater {
        model: Math.floor(root.totalMinutes / 30) + 1

        delegate: Item {
            readonly property int minute: index * 30
            readonly property bool major: (minute % 60) === 0
            readonly property real pct: (minute / root.totalMinutes)

            x: root.width * pct
            y: 0
            width: 1
            height: root.height

            Rectangle {
                x: -0.5
                y: 0
                width: 1
                height: parent.major ? 8 : 4
                color: Theme.border
            }

            Text {
                visible: parent.major
                x: 4
                y: 9
                text: Math.floor(parent.minute / 60) + ":" + (parent.minute % 60).toString().padStart(2, "0")
                color: Theme.ink4
                font.family: Theme.fontMono
                font.pixelSize: 10
            }
        }
    }

    // Segment split — vertical dashed line with a scissors badge.
    Item {
        id: splitMark
        x: root.width * (root.segmentSplitPct / 100.0)
        y: 0
        width: 0
        height: root.height

        // Dashed vertical line rendered via Shape (Qt Quick Rectangle
        // borders don't support dashes).
        Shape {
            anchors.fill: parent
            layer.enabled: true
            layer.samples: 4

            ShapePath {
                strokeColor: Theme.border
                strokeWidth: 1
                fillColor: "transparent"
                strokeStyle: ShapePath.DashLine
                dashPattern: [3, 3]
                startX: 0; startY: 0
                PathLine { x: 0; y: splitMark.height }
            }
        }

        // Scissors badge anchored over the line.
        Rectangle {
            x: -8
            y: -4
            width: 16
            height: 16
            radius: 999
            color: Theme.card
            border.width: 1
            border.color: Theme.border

            SvgIcon {
                anchors.centerIn: parent
                name: "scissors"; size: 9
                color: Theme.ink4
                strokeWidth: 1.8
            }
        }
    }
}
