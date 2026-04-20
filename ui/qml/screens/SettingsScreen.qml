import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App.Theme
import "../controls"

// App-level settings screen. Centered 760px form with a stack of
// SettingsGroup cards. Form controls keep local state only — real
// persistence lands with QSettings wiring in a later slice.
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
            implicitHeight: column.implicitHeight + 80

            ColumnLayout {
                id: column
                anchors.top: parent.top
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(parent.width - 80, 760)
                anchors.topMargin: 32
                spacing: 0

                Text {
                    Layout.fillWidth: true
                    text: "Настройки"
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    font.letterSpacing: -0.6
                }

                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    Layout.bottomMargin: 28
                    text: "Глобальные параметры приложения. Per-session параметры — на экране сессии."
                    color: Theme.ink3
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }

                // ── Working folder ────────────────────────────────
                SettingsGroup {
                    title: "Рабочая папка"
                    description: "Где хранятся файлы сессий, merged.txt и кэш ASR."

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        TextInputField {
                            Layout.fillWidth: true
                            mono: true
                            text: preferences.workingFolder
                            onEditingFinished: preferences.workingFolder = text
                        }

                        GhostButton {
                            sizeTag: "md"
                            iconName: "folderOpen"
                            text: "Выбрать…"
                            // Folder picker dialog lands with the drop-zone
                            // wiring in Phase 4; for now the input field
                            // is the authoritative source.
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.topMargin: -6
                        text: "Занято: —"  // disk-usage probe lands with session discovery
                        color: Theme.ink4
                        font.family: Theme.fontMono
                        font.pixelSize: 11
                    }
                }

                // ── Merger defaults ───────────────────────────────
                SettingsGroup {
                    title: "Мержер по умолчанию"
                    description: "Параметры сборки merged.txt. Применяются к новым сессиям."

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 14

                        SettingField {
                            Layout.fillWidth: true
                            label: "МАКС. GAP МЕЖДУ РЕПЛИКАМИ"
                            hint: "секунд — ближе склеивается"

                            TextInputField {
                                Layout.fillWidth: true
                                mono: true
                                text: preferences.mergerMaxGap
                                onEditingFinished: preferences.mergerMaxGap = text
                            }
                        }

                        SettingField {
                            Layout.fillWidth: true
                            label: "OOC В FOUNDRY-ЧАТЕ"

                            SelectField {
                                id: oocSelect
                                Layout.fillWidth: true
                                readonly property var values: ["skip", "italic", "include"]
                                model: [
                                    { v: "skip",    l: "Пропускать" },
                                    { v: "italic",  l: "Добавлять курсивом" },
                                    { v: "include", l: "Включать как обычные" }
                                ]
                                currentIndex: Math.max(0, values.indexOf(preferences.mergerOocMode))
                                onCurrentIndexChanged: {
                                    if (currentIndex >= 0)
                                        preferences.mergerOocMode = values[currentIndex]
                                }
                            }
                        }
                    }
                }

                // ── Interface ─────────────────────────────────────
                SettingsGroup {
                    title: "Интерфейс"

                    SettingField {
                        label: "ЯЗЫК"

                        SelectField {
                            id: langSelect
                            Layout.fillWidth: true
                            readonly property var values: ["ru", "en"]
                            model: [
                                { v: "ru", l: "Русский" },
                                { v: "en", l: "English" }
                            ]
                            currentIndex: Math.max(0, values.indexOf(preferences.interfaceLanguage))
                            onCurrentIndexChanged: {
                                if (currentIndex >= 0)
                                    preferences.interfaceLanguage = values[currentIndex]
                            }
                        }
                    }

                    CheckRow {
                        Layout.topMargin: 6
                        text: "Показывать подсказки в интерфейсе"
                        checked: preferences.showTooltips
                        onCheckedChanged: preferences.showTooltips = checked
                    }

                    CheckRow {
                        text: "Звуковое уведомление по завершении обработки"
                        checked: preferences.soundOnDone
                        onCheckedChanged: preferences.soundOnDone = checked
                    }
                }

                // ── About ─────────────────────────────────────────
                SettingsGroup {
                    title: "О программе"

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Text {
                            text: "Session Transcriber v0.4"
                            color: Theme.ink3
                            font.family: Theme.fontMono
                            font.pixelSize: 12
                        }
                        Text {
                            text: "Python 3.11 · Qt 6 / QML"
                            color: Theme.ink3
                            font.family: Theme.fontMono
                            font.pixelSize: 12
                        }
                        Text {
                            text: "Работает локально. Аудио не покидает компьютер."
                            color: Theme.ink3
                            font.family: Theme.fontMono
                            font.pixelSize: 12
                        }
                    }
                }
            }
        }
    }
}
