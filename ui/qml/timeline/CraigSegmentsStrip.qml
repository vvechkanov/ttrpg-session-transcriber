import QtQuick
import App.Theme

// Bottom strip of the timeline card: Craig's per-segment labels.
// Each segment is a soft grey pill with mono label. The gap between
// them corresponds to the Craig split point.
Item {
    id: root

    property int gutterWidth: 220
    property real segmentSplitPct: 66.0
    property string segment1Label: "Часть 1 · 0:00 → 2:30"
    property string segment2Label: "Часть 2 · 2:30 → 3:47"

    implicitHeight: 34

    // Gutter caption
    Rectangle {
        id: gutter
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.gutterWidth
        color: "transparent"

        Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 1
            color: Theme.borderSoft
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            x: 12
            text: "Craig сегменты"
            color: Theme.ink4
            font.family: Theme.fontMono
            font.pixelSize: 10
        }
    }

    // Segment pills
    Item {
        anchors.left: gutter.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: 6
        anchors.bottomMargin: 6

        // Part 1
        Rectangle {
            x: 0
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: parent.width * (root.segmentSplitPct / 100.0)
            radius: 3
            color: Theme.borderSoft

            Text {
                anchors.verticalCenter: parent.verticalCenter
                x: 8
                text: root.segment1Label
                color: Theme.ink3
                font.family: Theme.fontMono
                font.pixelSize: 10
            }
        }

        // Part 2 (small 0.3% gap matches the prototype)
        Rectangle {
            x: parent.width * ((root.segmentSplitPct + 0.3) / 100.0)
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: parent.width - x
            radius: 3
            color: Theme.borderSoft

            Text {
                anchors.verticalCenter: parent.verticalCenter
                x: 8
                text: root.segment2Label
                color: Theme.ink3
                font.family: Theme.fontMono
                font.pixelSize: 10
            }
        }
    }
}
