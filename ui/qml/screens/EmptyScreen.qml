import QtQuick
import QtQuick.Controls.Basic
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
                            }

                            GhostButton {
                                sizeTag: "md"
                                iconName: "folder"
                                text: "Собрать из нескольких"
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

                // ── Recent sessions header ────────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 40
                    Layout.bottomMargin: 16
                    Layout.leftMargin: 4
                    Layout.rightMargin: 4

                    Text {
                        Layout.fillWidth: true
                        text: "Недавние сессии"
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 15
                        font.weight: Font.Bold
                        font.letterSpacing: -0.2
                    }

                    // "все сессии →" link-button.
                    Item {
                        Layout.preferredWidth: allRow.implicitWidth + 10
                        Layout.preferredHeight: 20

                        RowLayout {
                            id: allRow
                            anchors.centerIn: parent
                            spacing: 4

                            Text {
                                text: "все сессии"
                                color: Theme.ink3
                                font.family: Theme.fontSans
                                font.pixelSize: 12
                            }
                            SvgIcon {
                                name: "chevRight"; size: 12
                                color: Theme.ink3
                                strokeWidth: 1.7
                            }
                        }

                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                    }
                }

                // ── Recent cards (wrap on narrow widths) ──────────
                Flow {
                    Layout.fillWidth: true
                    spacing: 16

                    RecentCard {
                        title: "Сессия 13 — Отступление"
                        meta: "7 апр · 3ч 12м · 5 игроков"
                        status: "done"
                        gradientFrom: Theme.accentSoft
                        gradientTo: Theme.accentWash
                    }
                    RecentCard {
                        title: "Сессия 12 — Таверна «Дракон»"
                        meta: "24 мар · 4ч 01м · 6 игроков"
                        status: "done"
                        gradientFrom: "#E6DCF2"
                        gradientTo: "#F3EDF9"
                    }
                    RecentCard {
                        title: "Сессия 14 — Битва на мосту"
                        meta: "10 апр · 3ч 47м · 6 игроков"
                        status: "draft"
                        gradientFrom: Theme.accentSoft
                        gradientTo: Theme.accentWash
                    }
                    RecentCard {
                        title: "Сессия 11 — Вход в Подгорье"
                        meta: "10 мар · 2ч 40м · 5 игроков"
                        status: "failed"
                        gradientFrom: Theme.redSoft
                        gradientTo: "#FCEEE8"
                    }
                }

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
