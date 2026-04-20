import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App.Theme
import "../controls"

// Right-edge drawer showing full details for one model row.
//
// Layout matches the prototype: header (icon + name + vendor line +
// close), three stat chips, a runtime-settings card (device segmented
// + precision/threads pair + VAD segmented + beam slider + checkboxes),
// and a bottom action stack.
//
// The runtime settings are layout-only for this slice — segmented
// buttons keep local state, but nothing persists through. Real per-
// model persistence lands with the ModelRegistry wiring step.
Drawer {
    id: drawer
    edge: Qt.RightEdge
    modal: true
    interactive: true
    width: Math.min(parent ? parent.width : 460, 460)
    height: parent ? parent.height : 0

    // Drop the default modal dim for a warm ink wash at 28% (prototype
    // uses rgba(45,37,32,0.28)).
    Overlay.modal: Rectangle {
        color: Qt.rgba(45/255, 37/255, 32/255, 0.28)
    }

    // Current model data as a QVariantMap from ModelRegistry.entryAt().
    property var modelData: null

    function openFor(data) {
        modelData = data
        open()
    }

    background: Rectangle {
        color: Theme.bg
        border.width: 1
        border.color: Theme.border
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: content
            width: parent.width
            spacing: 0

            // ── Header ──────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                color: Theme.card
                implicitHeight: hdrRow.implicitHeight + 32

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 1
                    color: Theme.borderSoft
                }

                RowLayout {
                    id: hdrRow
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 20
                    anchors.topMargin: 18
                    anchors.bottomMargin: 14
                    spacing: 12

                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        radius: 9
                        color: (drawer.modelData && drawer.modelData.installed) ? Theme.accentWash : Theme.cardAlt
                        border.width: 1
                        border.color: (drawer.modelData && drawer.modelData.installed) ? Theme.accentSoft : Theme.border

                        SvgIcon {
                            anchors.centerIn: parent
                            name: "cpu"
                            size: 19
                            strokeWidth: 1.7
                            color: (drawer.modelData && drawer.modelData.installed) ? Theme.accent : Theme.ink4
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            Layout.fillWidth: true
                            text: drawer.modelData ? drawer.modelData.name : ""
                            color: Theme.ink
                            font.family: Theme.fontSans
                            font.pixelSize: 16
                            font.weight: Font.Bold
                            font.letterSpacing: -0.2
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: drawer.modelData
                                ? drawer.modelData.vendor + " · " + drawer.modelData.size + " · " + drawer.modelData.lang
                                : ""
                            color: Theme.ink4
                            font.family: Theme.fontMono
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 28
                        Layout.preferredHeight: 28
                        radius: 6
                        color: closeMa.containsMouse ? Theme.cardAlt : "transparent"

                        SvgIcon {
                            anchors.centerIn: parent
                            name: "x"; size: 16
                            color: Theme.ink3
                            strokeWidth: 1.7
                        }
                        MouseArea {
                            id: closeMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: drawer.close()
                        }
                    }
                }
            }

            // ── Body ────────────────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.topMargin: 20
                Layout.bottomMargin: 20
                spacing: 16

                // Stat chips row
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Repeater {
                        model: drawer.modelData ? [
                            { k: "Точность", v: drawer.modelData.accuracy + "%",
                              tone: drawer.modelData.accuracy > 95 ? Theme.green : Theme.accent },
                            { k: "Скорость", v: drawer.modelData.speed,
                              tone: Theme.ink2 },
                            { k: "Размер",   v: drawer.modelData.size,
                              tone: Theme.ink2 }
                        ] : []

                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 56
                            radius: 9
                            color: Theme.card
                            border.width: 1
                            border.color: Theme.borderSoft

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                anchors.topMargin: 10
                                anchors.bottomMargin: 10
                                spacing: 3

                                Text {
                                    text: modelData.k
                                    color: Theme.ink4
                                    font.family: Theme.fontSans
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    font.letterSpacing: 0.6
                                }
                                Text {
                                    text: modelData.v
                                    color: modelData.tone
                                    font.family: Theme.fontMono
                                    font.pixelSize: 14
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }
                }

                // Runtime settings card
                Rectangle {
                    Layout.fillWidth: true
                    radius: 11
                    color: Theme.card
                    border.width: 1
                    border.color: Theme.border
                    implicitHeight: runtimeCol.implicitHeight + 32

                    ColumnLayout {
                        id: runtimeCol
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 13

                        Text {
                            text: "Параметры запуска"
                            color: Theme.ink
                            font.family: Theme.fontSans
                            font.pixelSize: 13
                            font.weight: Font.Bold
                        }
                        Text {
                            text: "Глобальные defaults этой модели. На дорожке можно переопределить."
                            color: Theme.ink3
                            font.family: Theme.fontSans
                            font.pixelSize: 11
                            Layout.bottomMargin: 1
                        }

                        MicroLabel { text: "УСТРОЙСТВО" }
                        SegmentedRow {
                            options: ["CPU", "CUDA", "MPS"]
                            disabledIndex: 2
                            currentIndex: 0
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                MicroLabel { text: "ТОЧНОСТЬ ВЕСОВ" }
                                ReadonlyField { text: "int8" }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                MicroLabel { text: "ПОТОКОВ CPU" }
                                ReadonlyField { text: "8" }
                            }
                        }

                        MicroLabel { text: "VAD" }
                        SegmentedRow {
                            options: ["выкл", "мягкий", "агрессивный"]
                            currentIndex: 1
                        }

                        MicroLabel { text: "BEAM SIZE" }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 4
                                radius: 2
                                color: Theme.borderSoft

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    width: parent.width * 0.40
                                    radius: 2
                                    color: Theme.accent
                                }
                                Rectangle {
                                    x: parent.width * 0.40 - 6
                                    y: -4
                                    width: 12; height: 12; radius: 999
                                    color: Theme.card
                                    border.width: 2
                                    border.color: Theme.accent
                                }
                            }
                            Text {
                                Layout.preferredWidth: 20
                                horizontalAlignment: Text.AlignRight
                                text: "5"
                                color: Theme.ink2
                                font.family: Theme.fontMono
                                font.pixelSize: 12
                            }
                        }

                        DrawerCheck { text: "Автоматическая пунктуация"; checked: true }
                        DrawerCheck { text: "Капитализация имён"; checked: true }
                        DrawerCheck { text: "Кэш результатов в сессии"; checked: false }
                    }
                }

                // Action stack
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    PrimaryButton {
                        Layout.fillWidth: true
                        visible: drawer.modelData && !drawer.modelData.active && drawer.modelData.installed
                        sizeTag: "md"
                        text: "Сделать активной"
                    }

                    PrimaryButton {
                        Layout.fillWidth: true
                        visible: drawer.modelData && !drawer.modelData.installed
                        sizeTag: "md"
                        iconName: "download"
                        text: drawer.modelData ? "Установить · " + drawer.modelData.size : ""
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        sizeTag: "sm"
                        iconName: "folder"
                        text: "Открыть папку модели"
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        visible: drawer.modelData && drawer.modelData.installed
                        sizeTag: "sm"
                        plain: true
                        danger: true
                        iconName: "trash"
                        text: "Удалить с диска"
                    }
                }
            }
        }
    }

    // ── Inline helper components ────────────────────────────────────
    component MicroLabel: Text {
        color: Theme.ink3
        font.family: Theme.fontSans
        font.pixelSize: 10
        font.weight: Font.Bold
        font.letterSpacing: 0.7
    }

    component ReadonlyField: Rectangle {
        property string text: ""
        Layout.fillWidth: true
        implicitHeight: 30
        radius: 7
        color: Theme.card
        border.width: 1
        border.color: Theme.border

        Text {
            anchors.fill: parent
            anchors.leftMargin: 10
            verticalAlignment: Text.AlignVCenter
            text: parent.text
            color: Theme.ink2
            font.family: Theme.fontMono
            font.pixelSize: 12
        }
    }

    component SegmentedRow: RowLayout {
        property var options: []
        property int currentIndex: 0
        property int disabledIndex: -1
        Layout.fillWidth: true
        spacing: 4

        Repeater {
            model: parent.options
            delegate: Rectangle {
                Layout.preferredHeight: 28
                implicitWidth: segText.implicitWidth + 24
                radius: 6

                readonly property bool isActive: index === parent.parent.currentIndex
                readonly property bool isDisabled: index === parent.parent.disabledIndex

                color: isActive ? Theme.accentWash : Theme.card
                border.width: 1
                border.color: isActive ? Theme.accentSoft : Theme.border
                opacity: isDisabled ? 0.5 : 1.0

                Text {
                    id: segText
                    anchors.centerIn: parent
                    text: modelData
                    color: isDisabled
                        ? Theme.ink4
                        : (isActive ? Theme.accentDeep : Theme.ink3)
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: isActive ? Font.DemiBold : Font.Medium
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: !parent.isDisabled
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: parent.parent.currentIndex = index
                }
            }
        }
    }

    component DrawerCheck: RowLayout {
        property string text: ""
        property bool checked: false
        Layout.fillWidth: true
        spacing: 8

        Rectangle {
            Layout.preferredWidth: 14
            Layout.preferredHeight: 14
            radius: 3
            border.width: 1
            border.color: parent.checked ? Theme.accent : Theme.border
            color: parent.checked ? Theme.accent : Theme.card

            SvgIcon {
                anchors.centerIn: parent
                visible: parent.parent.checked
                name: "check"
                size: 11
                color: Theme.accentFg
                strokeWidth: 2.2
            }
        }

        Text {
            Layout.fillWidth: true
            text: parent.text
            color: Theme.ink2
            font.family: Theme.fontSans
            font.pixelSize: 12
        }

        // RowLayout manages children's geometry, so anchors.fill on a
        // MouseArea is undefined behaviour. TapHandler listens on the
        // parent without owning the item's geometry.
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: parent.checked = !parent.checked }
    }
}
