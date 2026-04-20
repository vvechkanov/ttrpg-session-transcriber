import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import App.Theme
import "../controls"

// First-run / "no active session" dashboard.
//
// Layout (centered, 1200px max):
//   ┌ drop zone (big dashed card with stylized bars + CTA) ────┐
//   ┌ "Недавние сессии" row + "все сессии →" link              ─┐
//   │ RecentCard × 4 (wraps to next line on narrow widths)     │
//   ┌ first-install banner (gradient + zap + "Установить")     ─┘
Rectangle {
    id: root
    color: Theme.bg

    // Native OS folder picker triggered by "Выбрать папку…".
    // Mirrors Main.qml's window-wide DropArea: opens the session
    // via SessionMeta.openSession, THEN flips appModel.screen to
    // timeline. Without the screen flip the user stays on
    // EmptyScreen and the load looks silent ("ничего не происходит").
    FolderDialog {
        id: folderPicker
        title: "Выберите папку сессии"
        onAccepted: {
            if (typeof sessionMeta !== "undefined" && sessionMeta) {
                sessionMeta.openSession(selectedFolder.toString())
            }
            if (typeof appModel !== "undefined" && appModel) {
                appModel.screen = "timeline"
            }
        }
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: page.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Item {
            id: page
            width: parent.width
            implicitHeight: column.implicitHeight + 96

            ColumnLayout {
                id: column
                anchors.top: parent.top
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(parent.width - 96, 1200)
                anchors.topMargin: 48
                spacing: 0

                // ── Drop zone ─────────────────────────────────────
                Rectangle {
                    id: dropZone
                    Layout.fillWidth: true
                    radius: 16
                    color: Theme.card
                    border.width: 2
                    border.color: Theme.border
                    // Dashed border: Qt's Rectangle border is solid
                    // only. We approximate with a tiled Canvas stroke,
                    // but a solid 2px border reads fine on the warm
                    // palette and matches the prototype's feel at
                    // normal zoom. (A dashed Shape overlay can be
                    // swapped in if dashes become important.)

                    implicitHeight: dropCol.implicitHeight + 96

                    ColumnLayout {
                        id: dropCol
                        anchors.top: parent.top
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.topMargin: 48
                        width: Math.min(parent.width - 64, 520)
                        spacing: 0

                        // Stylized mini-timeline
                        RowLayout {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.bottomMargin: 22
                            spacing: 5

                            Repeater {
                                model: [0.3, 0.7, 0.45, 0.8, 0.5, 0.65]

                                delegate: Rectangle {
                                    width: 7
                                    height: 14 + 40 * modelData
                                    radius: 3
                                    opacity: 0.5 + modelData * 0.5
                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: Theme.accent }
                                        GradientStop { position: 1.0; color: Theme.accentSoft }
                                    }
                                }
                            }
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.bottomMargin: 8
                            text: "Перетащите папку сессии"
                            color: Theme.ink
                            font.family: Theme.fontSans
                            font.pixelSize: Theme.fontH1
                            font.weight: Font.Bold
                            font.letterSpacing: -0.4
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.bottomMargin: 20
                            Layout.maximumWidth: 440
                            text: "Архив Craig (.flac на игрока) + лог чата Foundry VTT.\nМы автоматически определим, что к чему."
                            color: Theme.ink3
                            font.family: Theme.fontSans
                            font.pixelSize: 14
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                        }

                        RowLayout {
                            Layout.alignment: Qt.AlignHCenter
                            spacing: 10

                            PrimaryButton {
                                sizeTag: "md"
                                iconName: "folderOpen"
                                text: "Выбрать папку…"
                                onClicked: folderPicker.open()
                            }

                            GhostButton {
                                sizeTag: "md"
                                iconName: "folder"
                                text: "Собрать из нескольких"
                                enabled: false
                                // Multi-folder selection: post-MVP.
                                // Native FolderDialog accepts one
                                // folder at a time; aggregating
                                // multiple roots needs its own
                                // picker flow.
                            }
                        }

                        RowLayout {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.topMargin: 18
                            spacing: 6

                            SvgIcon {
                                name: "info"; size: 11
                                color: Theme.ink4
                                strokeWidth: 1.5
                            }

                            Text {
                                text: "Распознаём: Craig .flac, Foundry chat .db, логи боя"
                                color: Theme.ink4
                                font.family: Theme.fontMono
                                font.pixelSize: 11
                            }
                        }
                    }
                }

                // "Недавние сессии" row removed in Phase 11 polish —
                // the mock card data (Сессия 13/12/14/11) was the
                // same fake content that tripped users into thinking
                // the app was running on fixtures. Real recent-sessions
                // wiring through core.recent_sessions is a post-MVP
                // follow-up; until then this area stays empty.

                // ── First-install banner ──────────────────────────
                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 32
                    radius: Theme.radiusLg
                    border.width: 1
                    border.color: Theme.accentSoft
                    implicitHeight: bannerRow.implicitHeight + 40

                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: Theme.accentWash }
                        GradientStop { position: 0.6; color: Theme.card }
                    }

                    RowLayout {
                        id: bannerRow
                        anchors.fill: parent
                        anchors.margins: 20
                        spacing: 20

                        Rectangle {
                            Layout.preferredWidth: 56
                            Layout.preferredHeight: 56
                            radius: 14
                            color: Theme.card
                            border.width: 1
                            border.color: Theme.accentSoft

                            SvgIcon {
                                anchors.centerIn: parent
                                name: "zap"; size: 26
                                color: Theme.accent
                                strokeWidth: 1.7
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            RowLayout {
                                spacing: 8

                                Text {
                                    text: "Готовы начать?"
                                    color: Theme.ink
                                    font.family: Theme.fontSans
                                    font.pixelSize: 14
                                    font.weight: Font.Bold
                                    font.letterSpacing: -0.2
                                }

                                Chip {
                                    tone: "accent"
                                    text: "первый запуск"
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: "Для распознавания русской речи рекомендуем <b>GigaAM-v3 RNNT</b> — 580 MB, лучшая точность для живой речи D&D. Установим её автоматически, когда вы запустите первую сессию."
                                textFormat: Text.RichText
                                color: Theme.ink2
                                font.family: Theme.fontSans
                                font.pixelSize: 13
                                wrapMode: Text.WordWrap
                                lineHeight: 1.5
                            }
                        }

                        SoftButton {
                            Layout.alignment: Qt.AlignVCenter
                            sizeTag: "md"
                            iconName: "download"
                            text: "Установить сейчас"
                        }
                    }
                }
            }
        }
    }
}
