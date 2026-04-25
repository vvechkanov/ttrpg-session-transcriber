import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Collapsible cast strip — header (chevron + "Cast" + count badge)
// and an optional body of pill labels showing every character name
// across the session's tracks.
//
// Used above the tracks Repeater on the Timeline screen. Defaults to
// collapsed; the user clicks the header to expand. Persistence of
// expansion across sessions is intentionally not implemented (YAGNI).
Item {
    id: root

    property int gutterWidth: 220
    //: De-duped, sorted union of every track row's characters. Drives
    //: both the count badge and the pill flow. Empty list collapses
    //: the strip to its header height; the body is hidden.
    property var characters: []

    //: Internal expansion state — header click toggles, no external
    //: setter (no use case yet).
    property bool _expanded: false

    readonly property int _count: characters ? characters.length : 0

    // Implicit height: header always visible (28 px). Body adds the
    // pill flow's implicitHeight + a 12 px top margin. We can't bind
    // to bodyFlow.implicitHeight directly when it's not visible since
    // hidden Flow children don't lay out — instead the body Item
    // carries implicit dimensions only while expanded.
    implicitHeight: 28 + (root._expanded && _count > 0
        ? (bodyContainer.implicitHeight + 12)
        : 0)

    // ── Header ────────────────────────────────────────────────────
    Item {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 28

        // Gutter caption (matches the other timeline strips)
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
                anchors.rightMargin: 12
                spacing: 6

                Item {
                    Layout.preferredWidth: 11
                    Layout.preferredHeight: 11

                    SvgIcon {
                        anchors.centerIn: parent
                        name: "chevRight"; size: 11
                        color: Theme.ink3
                        strokeWidth: 1.8
                        rotation: root._expanded ? 90 : 0
                        Behavior on rotation {
                            NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic }
                        }
                    }
                }

                Text {
                    text: "CAST"
                    color: Theme.ink3
                    font.family: Theme.fontSans
                    font.pixelSize: 10
                    font.weight: Font.Bold
                    font.letterSpacing: 1.0
                }

                Text {
                    text: "(" + root._count + ")"
                    color: Theme.ink4
                    font.family: Theme.fontMono
                    font.pixelSize: 10
                }

                Item { Layout.fillWidth: true }
            }
        }

        // Click target spans the entire header — gutter + body — so
        // the user can hit anywhere on the row to toggle.
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root._expanded = !root._expanded
        }
    }

    // ── Body (pills) ──────────────────────────────────────────────
    Item {
        id: bodyContainer
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.topMargin: 6
        visible: root._expanded && root._count > 0
        implicitHeight: bodyFlow.implicitHeight + 6

        Flow {
            id: bodyFlow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: root.gutterWidth + 4
            anchors.rightMargin: 12
            anchors.top: parent.top
            spacing: 6

            Repeater {
                model: root.characters

                delegate: Rectangle {
                    radius: Theme.radiusPill
                    color: Theme.accentWash
                    border.width: 1
                    border.color: Theme.accentSoft
                    implicitHeight: 22
                    implicitWidth: pillTxt.implicitWidth + 16

                    Text {
                        id: pillTxt
                        anchors.centerIn: parent
                        text: modelData
                        color: Theme.accentDeep
                        font.family: Theme.fontSans
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }
                }
            }
        }
    }
}
