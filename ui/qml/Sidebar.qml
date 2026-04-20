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

        // Flexible gap pushes the "Recent" block to the bottom.
        Item { Layout.fillHeight: true; Layout.fillWidth: true }

        // ── Recent sessions (only on Sessions group) ──────────────
        ColumnLayout {
            visible: root.currentScreen === "timeline" || root.currentScreen === "empty"
            Layout.fillWidth: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.bottomMargin: 14
            spacing: 6

            Text {
                text: "НЕДАВНИЕ"
                color: Theme.ink4
                font.family: Theme.fontSans
                font.pixelSize: Theme.fontMicro
                font.weight: Font.Bold
                font.letterSpacing: 1.2
            }

            // Placeholder data — real recent list comes from a model
            // later in the implementation order (ModelsScreen / Session
            // list step). Keeping it inline here preserves the visual
            // weight of the sidebar while we wire models up.
            Repeater {
                model: [
                    { date: "2025-01-14", name: "Сессия 14 · Мост Гоблинов", active: true },
                    { date: "2025-01-07", name: "Сессия 13 · Таверна",       active: false },
                    { date: "2024-12-20", name: "Сессия 12 · Пещера",        active: false }
                ]

                delegate: Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: column.implicitHeight + 12
                    radius: Theme.radiusSm
                    color: modelData.active ? Theme.cardAlt : "transparent"

                    // 2px left accent bar on the active item.
                    Rectangle {
                        visible: modelData.active
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: 2
                        color: Theme.accent
                    }

                    ColumnLayout {
                        id: column
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        anchors.topMargin: 6
                        anchors.bottomMargin: 6
                        spacing: 1

                        Text {
                            Layout.fillWidth: true
                            text: modelData.name
                            color: Theme.ink
                            font.family: Theme.fontSans
                            font.pixelSize: 11
                            font.weight: modelData.active ? Font.DemiBold : Font.Medium
                            elide: Text.ElideRight
                        }
                        Text {
                            text: modelData.date
                            color: Theme.ink4
                            font.family: Theme.fontMono
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }
    }
}
