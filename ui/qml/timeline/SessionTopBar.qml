import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Sticky top bar for the Timeline screen:
//   top mini-row — right-aligned CPU/GPU status
//   breadcrumb   — folder · campaign · > · session · segment chip
//   tabs         — Обработка / Транскрипт / Журнал / Настройки сессии
//
// Active tab is highlighted with a 2px accent underline that sits flush
// with the bar's bottom border.
Rectangle {
    id: root
    color: Qt.rgba(250/255, 248/255, 245/255, 0.92)  // bg @ 92%

    property string campaignTitle: ""
    property string sessionTitle: ""
    property string segmentsCaption: ""

    // "process" | "transcript" | "log" | "settings"
    property string activeTab: "process"
    signal tabActivated(string tab)

    implicitHeight: column.implicitHeight

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.borderSoft
    }

    ColumnLayout {
        id: column
        anchors.fill: parent
        spacing: 0

        // ── Top status strip ──────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            spacing: 16

            Item { Layout.fillWidth: true }

            Text {
                text: (typeof preferences !== "undefined" && preferences && preferences.asrDevice === "cuda")
                    ? "GPU"
                    : "CPU"
                color: Theme.ink3
                font.family: Theme.fontMono
                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 12
                color: Theme.border
            }

            RowLayout {
                spacing: 5

                Rectangle {
                    Layout.preferredWidth: 6
                    Layout.preferredHeight: 6
                    radius: 6
                    color: Theme.green
                }

                Text {
                    text: "готов"
                    color: Theme.green
                    font.family: Theme.fontMono
                    font.pixelSize: 11
                }
            }
        }

        // ── Breadcrumb ────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            Layout.topMargin: -2
            Layout.bottomMargin: 8
            spacing: 6

            SvgIcon {
                name: "folder"; size: 13
                color: Theme.ink4
                strokeWidth: 1.6
            }

            Text {
                text: root.campaignTitle
                color: Theme.ink2
                font.family: Theme.fontSans
                font.pixelSize: 12
            }

            SvgIcon {
                name: "chevRight"; size: 11
                color: Theme.inkFaint
                strokeWidth: 1.7
            }

            Text {
                text: root.sessionTitle
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.weight: Font.DemiBold
            }

            Chip {
                Layout.leftMargin: 8
                tone: "neutral"
                text: root.segmentsCaption
            }

            Item { Layout.fillWidth: true }
        }

        // ── Tabs ──────────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            spacing: 2

            Repeater {
                model: [
                    { id: "process",    label: "Обработка" },
                    { id: "transcript", label: "Транскрипт" },
                    { id: "log",        label: "Журнал" },
                    { id: "settings",   label: "Настройки сессии" }
                ]

                delegate: Item {
                    readonly property bool isActive: modelData.id === root.activeTab
                    implicitWidth: tabText.implicitWidth + 28
                    implicitHeight: 36

                    Text {
                        id: tabText
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: -1
                        text: modelData.label
                        color: parent.isActive ? Theme.ink : Theme.ink3
                        font.family: Theme.fontSans
                        font.pixelSize: 13
                        font.weight: parent.isActive ? Font.DemiBold : Font.Medium
                        font.letterSpacing: -0.05
                    }

                    Rectangle {
                        visible: parent.isActive
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 2
                        color: Theme.accent
                    }

                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: root.tabActivated(modelData.id) }
                }
            }

            Item { Layout.fillWidth: true }
        }
    }
}
