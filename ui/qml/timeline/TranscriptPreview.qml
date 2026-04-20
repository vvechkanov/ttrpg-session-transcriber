import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// merged.txt summary card shown below the timeline on done phase.
//
// Layout:
//   ┌─ paper-sheet icon ─── filename + "готов" chip + mono stats line
//   │                        + muted path                 ───── open btn
//   │                                                           folder btn
//
// The paper-sheet icon is drawn inline (not an SVG) — a small Rect
// with a folded-corner triangle and five line-strokes simulates a
// text document at that size.
Rectangle {
    id: root

    property string filePath: ""
    property string fileSize: ""
    property string wordCount: ""
    property string cueCount: ""
    property string sessionLength: ""

    signal openClicked()
    signal revealInFolderClicked()

    Layout.fillWidth: true
    radius: Theme.radiusLg
    color: Theme.card
    border.width: 1
    border.color: Theme.border
    implicitHeight: row.implicitHeight + 28

    readonly property string _fileName: {
        const parts = filePath.split("/")
        return parts.length > 0 ? parts[parts.length - 1] : "merged.txt"
    }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 14
        spacing: 14

        // ── Paper-sheet icon ──────────────────────────────────────
        Item {
            Layout.preferredWidth: 44
            Layout.preferredHeight: 54

            Rectangle {
                anchors.fill: parent
                radius: 4
                color: Theme.card
                border.width: 1
                border.color: Theme.border

                // Folded top-right corner
                Rectangle {
                    x: parent.width - width
                    y: 0
                    width: 14
                    height: 14
                    color: Theme.cardAlt
                    // Use a pair of L-shaped borders to suggest the fold.
                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: 1
                        color: Theme.border
                    }
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 1
                        color: Theme.border
                    }
                }

                // Five text lines
                Column {
                    x: 6
                    y: 20
                    spacing: 3

                    Repeater {
                        model: [0.8, 1.0, 0.7, 0.9, 0.6]

                        delegate: Rectangle {
                            width: (44 - 12) * modelData
                            height: 2
                            radius: 1
                            color: Theme.border
                        }
                    }
                }
            }
        }

        // ── File meta block ───────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4

            RowLayout {
                spacing: 8

                Text {
                    text: root._fileName
                    color: Theme.ink
                    font.family: Theme.fontMono
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    font.letterSpacing: -0.2
                }

                Chip {
                    tone: "green"
                    text: "готов"
                    dot: true
                }
            }

            // Mono stats flow: size • words • cues • length. The prototype
            // separates them with a dot; we use RowLayout with dot
            // widgets for tight alignment and wrapping fallback.
            Flow {
                Layout.fillWidth: true
                spacing: 10

                Text {
                    text: root.fileSize
                    color: Theme.ink3
                    font.family: Theme.fontMono
                    font.pixelSize: 12
                }
                Text { text: "•"; color: Theme.inkFaint; font.family: Theme.fontMono; font.pixelSize: 12 }
                Text {
                    text: root.wordCount
                    color: Theme.ink3
                    font.family: Theme.fontMono
                    font.pixelSize: 12
                }
                Text { text: "•"; color: Theme.inkFaint; font.family: Theme.fontMono; font.pixelSize: 12 }
                Text {
                    text: root.cueCount
                    color: Theme.ink3
                    font.family: Theme.fontMono
                    font.pixelSize: 12
                }
                Text { text: "•"; color: Theme.inkFaint; font.family: Theme.fontMono; font.pixelSize: 12 }
                Text {
                    text: root.sessionLength
                    color: Theme.ink3
                    font.family: Theme.fontMono
                    font.pixelSize: 12
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.filePath
                color: Theme.ink4
                font.family: Theme.fontMono
                font.pixelSize: 11
                elide: Text.ElideRight
            }
        }

        // ── Action stack ──────────────────────────────────────────
        ColumnLayout {
            spacing: 6

            PrimaryButton {
                sizeTag: "sm"
                iconName: "externalLink"
                text: "Открыть"
                onClicked: root.openClicked()
            }

            GhostButton {
                sizeTag: "sm"
                iconName: "folderOpen"
                text: "В папке"
                onClicked: root.revealInFolderClicked()
            }
        }
    }
}
