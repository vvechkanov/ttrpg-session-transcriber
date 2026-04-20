import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// One recent-session card on the EmptyScreen dashboard.
//
// Layout: preview strip (72px tall, gradient bg, ghost waveform bars)
// over a content block (title, mono meta line, status chip).
//
// `status` drives which chip renders:
//   "done"   → green "готов"
//   "draft"  → neutral "черновик"
//   "failed" → red "ошибка"
Rectangle {
    id: root

    property string title: ""
    property string meta: ""
    property string status: "done"
    property color gradientFrom: Theme.accentSoft
    property color gradientTo: Theme.accentWash

    width: 240
    implicitHeight: column.implicitHeight + preview.height

    radius: Theme.radiusLg
    color: Theme.card
    border.width: 1
    border.color: Theme.border
    clip: true

    scale: hoverMa.containsMouse ? 1.0 : 1.0  // translateY handled via y-binding
    y: hoverMa.containsMouse ? -2 : 0
    Behavior on y { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic } }

    Rectangle {
        id: preview
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 72

        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: root.gradientFrom }
            GradientStop { position: 1.0; color: root.gradientTo }
        }

        // Ghost-waveform bars across the preview — same 6-bar silhouette
        // the prototype renders with positioned div slices.
        Row {
            anchors.left: parent.left
            anchors.leftMargin: 10
            anchors.top: parent.top
            anchors.topMargin: 8
            spacing: 4

            Repeater {
                model: [0.4, 0.6, 0.35, 0.55, 0.45, 0.3]

                delegate: Item {
                    width: 32
                    height: 54

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: parent.height * modelData
                        radius: 2
                        color: Qt.rgba(1, 1, 1, 0.7)
                    }
                }
            }
        }
    }

    ColumnLayout {
        id: column
        anchors.top: preview.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        anchors.topMargin: 14
        anchors.bottomMargin: 14
        spacing: 4

        Text {
            Layout.fillWidth: true
            text: root.title
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: 14
            font.weight: Font.DemiBold
            font.letterSpacing: -0.15
            elide: Text.ElideRight
        }

        Text {
            Layout.fillWidth: true
            Layout.bottomMargin: 6
            text: root.meta
            color: Theme.ink3
            font.family: Theme.fontMono
            font.pixelSize: 11
        }

        Chip {
            tone: root.status === "done"
                ? "green"
                : (root.status === "failed" ? "red" : "neutral")
            text: root.status === "done"
                ? "готов"
                : (root.status === "failed" ? "ошибка" : "черновик")
        }
    }

    MouseArea {
        id: hoverMa
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
    }
}
