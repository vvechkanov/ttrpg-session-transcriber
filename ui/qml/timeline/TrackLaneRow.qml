import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"
import "../controls/PlayerHues.js" as Hues

// One track (audio lane) row. Left gutter: avatar (initial in hue
// colour) + name / role / character line + per-track model badge. Right
// column: waveform with the Craig segment split drawn across.
//
// Excluded (listener) tracks render at 45% opacity with a muted avatar
// and the italic "слушатель · не ASR" caption.
Item {
    id: root

    property int gutterWidth: 220
    property real segmentSplitPct: 66.0

    property string playerName: ""
    property string playerRole: ""
    property string character: ""
    property bool excluded: false
    property string modelId: ""
    property bool modelOverride: false
    property var peaks: []

    signal modelBadgeClicked()

    implicitHeight: 54
    opacity: excluded ? 0.45 : 1.0

    readonly property var hue: Hues.forName(playerName)

    // Row separator
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.borderSoft
    }

    // ── Left gutter ───────────────────────────────────────────────
    Rectangle {
        id: gutter
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.gutterWidth
        color: "transparent"

        // Right divider
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
            anchors.rightMargin: 10
            spacing: 9

            // Avatar
            Rectangle {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                radius: 999
                color: root.excluded ? Theme.cardAlt : root.hue.base
                border.width: root.excluded ? 1 : 0
                border.color: Theme.border

                Text {
                    anchors.centerIn: parent
                    text: root.playerName.length > 0 ? root.playerName.charAt(0) : ""
                    color: root.excluded ? Theme.ink4 : Theme.accentFg
                    font.family: Theme.fontSans
                    font.pixelSize: 11
                    font.weight: Font.Bold
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    Layout.fillWidth: true
                    text: root.playerName
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    font.letterSpacing: -0.05
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: root.excluded
                        ? "слушатель · не ASR"
                        : (root.playerRole + " · " + root.character)
                    color: Theme.ink3
                    font.family: Theme.fontSans
                    font.pixelSize: 10
                    font.italic: root.excluded
                    elide: Text.ElideRight
                }
            }

            // Model badge (hidden for listeners)
            Rectangle {
                id: modelBadge
                visible: !root.excluded
                Layout.preferredHeight: 18
                implicitWidth: badgeRow.implicitWidth + 12
                radius: Theme.radiusSm
                color: root.modelOverride ? Theme.accentWash : "transparent"
                border.width: 1
                border.color: root.modelOverride ? Theme.accentSoft : Theme.border

                RowLayout {
                    id: badgeRow
                    anchors.centerIn: parent
                    spacing: 3

                    Text {
                        text: root.modelId === "whisper" ? "Whs" : "gAM"
                        color: root.modelOverride ? Theme.accentDeep : Theme.ink3
                        font.family: Theme.fontMono
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.3
                    }

                    SvgIcon {
                        visible: root.modelOverride
                        name: "alert"; size: 9
                        color: Theme.accentDeep
                        strokeWidth: 2.0
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.modelBadgeClicked()
                }
            }
        }
    }

    // ── Right: waveform + segment split ───────────────────────────
    Item {
        id: track
        anchors.left: gutter.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: 6
        anchors.bottomMargin: 6

        WaveformMock {
            anchors.fill: parent
            peaks: root.peaks
            muted: root.excluded
        }

        // Vertical dashed segment-split line across the waveform.
        Rectangle {
            x: track.width * (root.segmentSplitPct / 100.0) - 0.5
            y: -6
            width: 1
            height: track.height + 12
            color: "transparent"

            // Render dashes with a pair of semi-transparent children —
            // Rectangle has no dash support. A 1px dashed line is
            // visually subtle enough that four segments read as dashed.
            Repeater {
                model: 18

                delegate: Rectangle {
                    x: 0
                    y: index * ((track.height + 12) / 18)
                    width: 1
                    height: (track.height + 12) / 18 / 2
                    color: Theme.border
                }
            }
        }
    }
}
