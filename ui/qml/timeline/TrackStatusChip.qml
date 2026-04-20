import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Small inline chip anchored to the bottom of a TrackLaneRow's
// waveform, shown only while the pipeline is active. Swaps
// presentation by `trackState`:
//
//   running → accent chip with pulsing dot + "ASR · XX%"
//   cached  → green chip with check + "из кэша"
//   failed  → red chip with alert + message
//   queued  → plain mono "в очереди" (no bubble)
//
// The outer item stays a constant 20px tall so it doesn't push the
// waveform around as the chip changes variant.
Item {
    id: root

    property string trackState: "queued"
    property real progress: 0.0
    property string errorMessage: ""

    implicitHeight: 20

    // ── Running ───────────────────────────────────────────────────
    Rectangle {
        visible: root.trackState === "running"
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        height: 20
        implicitWidth: runRow.implicitWidth + 14
        radius: Theme.radiusSm - 1
        color: Qt.rgba(1, 1, 1, 0.95)
        border.width: 1
        border.color: Theme.accentSoft

        RowLayout {
            id: runRow
            anchors.fill: parent
            anchors.leftMargin: 7
            anchors.rightMargin: 7
            spacing: 5

            Rectangle {
                Layout.preferredWidth: 5
                Layout.preferredHeight: 5
                radius: 5
                color: Theme.accent

                SequentialAnimation on opacity {
                    loops: Animation.Infinite
                    NumberAnimation { from: 1.0; to: 0.3; duration: 600 }
                    NumberAnimation { from: 0.3; to: 1.0; duration: 600 }
                }
            }

            Text {
                text: "ASR · " + Math.round(root.progress * 100) + "%"
                color: Theme.accentDeep
                font.family: Theme.fontMono
                font.pixelSize: 10
                font.weight: Font.DemiBold
            }
        }
    }

    // ── Cached ────────────────────────────────────────────────────
    Rectangle {
        visible: root.trackState === "cached"
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        height: 20
        implicitWidth: cacheRow.implicitWidth + 14
        radius: Theme.radiusSm - 1
        color: Qt.rgba(1, 1, 1, 0.95)
        border.width: 1
        border.color: Qt.rgba(90/255, 138/255, 62/255, 0.35)

        RowLayout {
            id: cacheRow
            anchors.fill: parent
            anchors.leftMargin: 7
            anchors.rightMargin: 7
            spacing: 5

            SvgIcon {
                name: "check"; size: 10
                color: Theme.green
                strokeWidth: 2.4
            }
            Text {
                text: "из кэша"
                color: Theme.green
                font.family: Theme.fontMono
                font.pixelSize: 10
                font.weight: Font.DemiBold
            }
        }
    }

    // ── Failed ────────────────────────────────────────────────────
    Rectangle {
        visible: root.trackState === "failed"
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        height: 20
        implicitWidth: failRow.implicitWidth + 14
        radius: Theme.radiusSm - 1
        color: Qt.rgba(1, 1, 1, 0.95)
        border.width: 1
        border.color: Theme.redSoft

        RowLayout {
            id: failRow
            anchors.fill: parent
            anchors.leftMargin: 7
            anchors.rightMargin: 7
            spacing: 5

            SvgIcon {
                name: "alert"; size: 10
                color: Theme.red
                strokeWidth: 2.2
            }
            Text {
                text: root.errorMessage.length > 0
                    ? root.errorMessage
                    : "ошибка распознавания"
                color: Theme.red
                font.family: Theme.fontMono
                font.pixelSize: 10
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
        }
    }

    // ── Queued (plain) ────────────────────────────────────────────
    Text {
        visible: root.trackState === "queued"
        anchors.left: parent.left
        anchors.leftMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        text: "в очереди"
        color: Theme.ink4
        font.family: Theme.fontMono
        font.pixelSize: 10
    }
}
