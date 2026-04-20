import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"
import "ParserBadges.js" as Parsers

// One additional-source lane (chat / combat / notes). Left gutter
// holds the parser icon + title line + file name; the right column
// draws a range bar spanning [startPct..endPct] of the timeline with
// random tick marks to suggest content density.
Item {
    id: root

    property int gutterWidth: 220
    property string parserId: "foundry-chat"
    property string sourceLabel: ""
    property string fileName: ""
    property real startPct: 0.0
    property real endPct: 100.0

    // Dimmed state — used later when ASR is running; unused in the
    // idle slice but the prop is available so TimelineScreen can flip
    // it once the phase wires up.
    property bool dim: false

    implicitHeight: 30
    opacity: dim ? 0.5 : 1.0
    Behavior on opacity { NumberAnimation { duration: Theme.animMed } }

    readonly property var parser: Parsers.forId(parserId)
    readonly property string _short: Parsers.shortLabel(parserId)

    // ── Gutter: icon + title + file ───────────────────────────────
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

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 6
            spacing: 8

            SvgIcon {
                name: root.parser.icon
                size: 13
                color: root.parser.color
                strokeWidth: 1.7
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: root._short
                        color: Theme.ink2
                        font.family: Theme.fontSans
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        font.letterSpacing: -0.05
                        elide: Text.ElideRight
                    }
                    Text {
                        text: "· " + root.sourceLabel
                        color: Theme.ink4
                        font.family: Theme.fontSans
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                    Item { Layout.fillWidth: true }
                }

                Text {
                    Layout.fillWidth: true
                    text: root.fileName
                    color: Theme.ink4
                    font.family: Theme.fontMono
                    font.pixelSize: 10
                    elide: Text.ElideRight
                }
            }
        }
    }

    // ── Range bar in the right column ─────────────────────────────
    Item {
        id: track
        anchors.left: gutter.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: 5
        anchors.bottomMargin: 5

        Rectangle {
            x: track.width * (root.startPct / 100.0)
            y: 1
            width: track.width * Math.max(0, (root.endPct - root.startPct) / 100.0)
            height: track.height - 2
            radius: 4

            // parser color at low alpha for the fill, stronger for the
            // border. Hex-alpha (#RRGGBBAA) works in Qt.
            color: Qt.rgba(1, 1, 1, 0)
            border.width: 1

            readonly property color _c: root.parser.color

            Component.onCompleted: {
                // Parse the hex color and apply alpha programmatically.
                color = Qt.rgba(_c.r, _c.g, _c.b, 0.07)
                border.color = Qt.rgba(_c.r, _c.g, _c.b, 0.27)
            }

            // Random tick marks (content density suggestion). Seeded
            // so the same source always shows the same pattern.
            Repeater {
                model: root.parserId === "combat-log" ? 18 : 12

                delegate: Rectangle {
                    // Pseudo-random position within the range bar,
                    // derived from index + parserId chars.
                    readonly property int _seed:
                        (root.parserId.charCodeAt(0)
                         + root.parserId.charCodeAt(1) + index * 7919) % 997

                    x: parent.width * (_seed / 997.0)
                    y: 2
                    width: 1
                    height: parent.height - 4
                    color: root.parser.color
                    opacity: 0.55
                }
            }
        }
    }
}
