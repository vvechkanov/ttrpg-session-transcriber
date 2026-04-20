import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import App.Theme

// Global sidebar — primary navigation across app screens.
//
// Mirrors the prototype's <AppSidebar>: brand badge + version, three
// nav items (Sessions / Models / Settings), and a "Recent" block shown
// only while the Sessions-group screen (timeline or empty) is active.
//
// The sidebar is intentionally dumb: it reads `currentScreen` and emits
// `navigate(name)`. Main.qml wires that to `appModel.screen`.
Rectangle {
    id: root
    width: Theme.sidebarWidth
    color: Theme.card

    // External API
    property string currentScreen: "timeline"
    signal navigate(string screen)

    // Right-edge divider — drawn as a 1px strip so the border stays
    // crisp regardless of window DPR.
    Rectangle {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 1
        color: Theme.border
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Brand header ──────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 16
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.bottomMargin: 14
            spacing: 9

            Rectangle {
                width: 26; height: 26
                radius: 7
                color: Theme.accent
                Text {
                    anchors.centerIn: parent
                    text: "ST"
                    color: Theme.accentFg
                    font.family: Theme.fontSans
                    font.pixelSize: 11
                    font.weight: Font.ExtraBold
                    font.letterSpacing: -0.3
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: "Session Transcriber"
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                    font.weight: Font.Bold
                    font.letterSpacing: -0.2
                    elide: Text.ElideRight
                }

                Text {
                    text: "v0.4 · offline"
                    color: Theme.ink4
                    font.family: Theme.fontMono
                    font.pixelSize: 10
                    font.letterSpacing: 0.2
                }
            }
        }

        // ── Nav items ─────────────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            spacing: 2

            Repeater {
                model: [
                    { key: "timeline", label: "Сессии",    icon: "list" },
                    { key: "models",   label: "Модели",    icon: "zap" },
                    { key: "settings", label: "Настройки", icon: "settings" }
                ]

                delegate: SidebarNavButton {
                    Layout.fillWidth: true
                    itemKey: modelData.key
                    itemLabel: modelData.label
                    iconName: modelData.icon
                    // "empty" belongs to the Sessions group.
                    active: (root.currentScreen === modelData.key)
                        || (modelData.key === "timeline" && root.currentScreen === "empty")
                    onClicked: root.navigate(modelData.key)
                }
            }
        }

        // Flexible gap pushes everything to the top.
        Item { Layout.fillHeight: true; Layout.fillWidth: true }

        // "НЕДАВНИЕ" sidebar block removed in Phase 11 polish — the
        // hardcoded three-item list was the prototype's placeholder
        // data. A real recent-sessions model (core.recent_sessions
        // already has the storage) is a post-MVP follow-up.
    }
}
