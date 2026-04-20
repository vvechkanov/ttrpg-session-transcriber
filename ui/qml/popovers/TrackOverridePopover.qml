import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App.Theme
import "../controls"
import "../controls/PlayerHues.js" as Hues

// Per-track ASR model override popover.
//
// Uses Qt Quick Controls' `Popup` so dismissal semantics come for
// free: `modal` + `closePolicy: OutsideOrEscape` handles the outside-
// click + ESC behaviour the handoff calls for.
//
// Opening:
//     popover.openFor(row, trackName, modelId, override)
//
// Committed selection is reported via the `chosen(row, optionId)`
// signal; the caller mutates TrackListModel.
Popup {
    id: root

    // Model row to update. -1 means "nothing bound" — the popover
    // should be closed in that state.
    property int targetRow: -1
    property string trackName: ""
    property string currentModelId: ""
    property bool currentOverride: false

    width: 380
    padding: 0

    modal: true
    dim: false
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

    signal chosen(int row, string optionId)

    function openFor(row, name, modelId, override) {
        targetRow = row
        trackName = name
        currentModelId = modelId
        currentOverride = override
        _pendingId = _currentOptionId()
        _advanced = false
        open()
    }

    // Which radio option matches the track's current model state.
    function _currentOptionId() {
        if (!currentOverride) return "default"
        if (currentModelId === "whisper") return "whisper-med"
        return "gigaam"
    }

    property string _pendingId: "default"
    property bool _advanced: false

    readonly property var _hue: Hues.forName(trackName)
    readonly property var _options: [
        { id: "default",     title: "Как у всех (GigaAM-v3 int8)", note: "Активная по умолчанию" },
        { id: "gigaam",      title: "GigaAM-v3 RNNT",              note: "Быстро, RU, 420 MB" },
        { id: "whisper-med", title: "faster-whisper medium",       note: "Точнее для тихой речи, RU/EN" },
        { id: "whisper-lg",  title: "faster-whisper large-v3",     note: "Максимум точности, медленно" }
    ]

    background: Rectangle {
        radius: Theme.radiusLg
        color: Theme.card
        border.width: 1
        border.color: Theme.border
        // Soft warm drop shadow — approximated with a faint second
        // rectangle since Qt Rectangle has no CSS-style shadow.
        Rectangle {
            z: -1
            anchors.fill: parent
            anchors.margins: -6
            radius: parent.radius + 2
            color: Qt.rgba(45/255, 37/255, 32/255, 0.12)
            opacity: 0.35
        }
    }

    contentItem: ColumnLayout {
        spacing: 0

        // ── Header ──────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 14
            spacing: 10

            Rectangle {
                Layout.preferredWidth: 26
                Layout.preferredHeight: 26
                radius: 999
                color: root._hue.base

                Text {
                    anchors.centerIn: parent
                    text: root.trackName.length > 0 ? root.trackName.charAt(0) : ""
                    color: Theme.accentFg
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
                    text: "Модель для " + root.trackName
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: Font.Bold
                }
                Text {
                    Layout.fillWidth: true
                    text: "Переопределяет модель по умолчанию только на этой дорожке"
                    color: Theme.ink4
                    font.family: Theme.fontSans
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }
            }

            Rectangle {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                radius: 4
                color: closeMa.containsMouse ? Theme.cardAlt : "transparent"

                SvgIcon {
                    anchors.centerIn: parent
                    name: "x"; size: 14
                    color: Theme.ink4
                    strokeWidth: 1.8
                }
                MouseArea {
                    id: closeMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.close()
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.borderSoft
        }

        // ── Model options ───────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: 10
            spacing: 2

            Repeater {
                model: root._options

                delegate: Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: optionRow.implicitHeight + 16
                    radius: Theme.radiusSm + 1

                    readonly property bool isActive: modelData.id === root._pendingId
                    color: isActive
                        ? Theme.accentWash
                        : (optionMa.containsMouse ? Theme.cardAlt : "transparent")
                    border.width: 1
                    border.color: isActive ? Theme.accentSoft : "transparent"

                    Behavior on color { ColorAnimation { duration: Theme.animFast } }

                    RowLayout {
                        id: optionRow
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 10

                        // Radio dot
                        Rectangle {
                            Layout.preferredWidth: 14
                            Layout.preferredHeight: 14
                            radius: 999
                            border.width: 1.5
                            border.color: parent.parent.isActive ? Theme.accent : Theme.border
                            color: parent.parent.isActive ? Theme.accent : "transparent"

                            Rectangle {
                                visible: parent.parent.parent.isActive
                                anchors.centerIn: parent
                                width: 5; height: 5; radius: 5
                                color: Theme.accentFg
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1

                            Text {
                                Layout.fillWidth: true
                                text: modelData.title
                                color: Theme.ink
                                font.family: Theme.fontSans
                                font.pixelSize: 12
                                font.weight: parent.parent.parent.isActive ? Font.DemiBold : Font.Medium
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData.note
                                color: Theme.ink4
                                font.family: Theme.fontSans
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                        }
                    }

                    MouseArea {
                        id: optionMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root._pendingId = modelData.id
                    }
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.borderSoft
        }

        // ── Advanced toggle ─────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: 14
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Item {
                    Layout.preferredWidth: 11
                    Layout.preferredHeight: 11

                    SvgIcon {
                        anchors.centerIn: parent
                        name: "chevRight"; size: 11
                        color: Theme.ink3
                        strokeWidth: 1.8

                        // 90° rotation when the advanced block is open.
                        rotation: root._advanced ? 90 : 0
                        Behavior on rotation {
                            NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic }
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: "Расширенные параметры распознавания"
                    color: Theme.ink3
                    font.family: Theme.fontSans
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
            }

            MouseArea {
                width: parent.width
                height: 20
                y: -20
                cursorShape: Qt.PointingHandCursor
                onClicked: root._advanced = !root._advanced
            }

            // Advanced body — shown layout-only; persistence for per-
            // track VAD / beam / prompt lands with the core wiring.
            ColumnLayout {
                visible: root._advanced
                Layout.fillWidth: true
                Layout.topMargin: 10
                spacing: 10

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5

                    Text {
                        text: "VAD (ОБРЕЗАТЬ ТИШИНУ)"
                        color: Theme.ink3
                        font.family: Theme.fontSans
                        font.pixelSize: 10
                        font.weight: Font.Bold
                        font.letterSpacing: 0.7
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Repeater {
                            model: ["выкл", "мягкий", "агрессивный"]

                            delegate: Rectangle {
                                readonly property bool isActive: index === 2
                                implicitHeight: 26
                                implicitWidth: tagTxt.implicitWidth + 18
                                radius: 5
                                color: isActive ? Theme.accentWash : Theme.card
                                border.width: 1
                                border.color: isActive ? Theme.accentSoft : Theme.border

                                Text {
                                    id: tagTxt
                                    anchors.centerIn: parent
                                    text: modelData
                                    color: parent.isActive ? Theme.accentDeep : Theme.ink3
                                    font.family: Theme.fontSans
                                    font.pixelSize: 11
                                    font.weight: parent.isActive ? Font.DemiBold : Font.Medium
                                }
                            }
                        }
                    }

                    Text {
                        visible: root.trackName === "Carol"
                        text: "Carol говорит тихо — рекомендуем «агрессивный»"
                        color: Theme.ink4
                        font.family: Theme.fontSans
                        font.pixelSize: 10
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5

                        Text {
                            text: "BEAM SIZE"
                            color: Theme.ink3
                            font.family: Theme.fontSans
                            font.pixelSize: 10
                            font.weight: Font.Bold
                            font.letterSpacing: 0.7
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 26
                            radius: 6
                            color: Theme.card
                            border.width: 1
                            border.color: Theme.border

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                x: 9
                                text: "5"
                                color: Theme.ink2
                                font.family: Theme.fontMono
                                font.pixelSize: 12
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5

                        Text {
                            text: "ЯЗЫК"
                            color: Theme.ink3
                            font.family: Theme.fontSans
                            font.pixelSize: 10
                            font.weight: Font.Bold
                            font.letterSpacing: 0.7
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 26
                            radius: 6
                            color: Theme.card
                            border.width: 1
                            border.color: Theme.border

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                x: 9
                                text: "Русский"
                                color: Theme.ink2
                                font.family: Theme.fontSans
                                font.pixelSize: 12
                            }
                        }
                    }
                }

                CheckRow {
                    text: "Пунктуация и капитализация"
                    checked: true
                }
            }
        }

        // ── Footer ──────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            color: Theme.cardAlt
            implicitHeight: footerRow.implicitHeight + 20

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 1
                color: Theme.borderSoft
            }

            RowLayout {
                id: footerRow
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                anchors.topMargin: 10
                anchors.bottomMargin: 10
                spacing: 8

                GhostButton {
                    sizeTag: "sm"
                    plain: true
                    text: "Сбросить к дефолтам"
                    onClicked: {
                        root._pendingId = "default"
                    }
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    sizeTag: "sm"
                    text: "Готово"
                    onClicked: {
                        if (root.targetRow >= 0) {
                            root.chosen(root.targetRow, root._pendingId)
                        }
                        root.close()
                    }
                }
            }
        }
    }
}
