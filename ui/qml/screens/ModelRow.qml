import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// One row in the Models table. Mirrors the prototype's grid columns:
//   2.6fr        — name + vendor + "активна" chip + icon
//    90px        — size (mono)
//    70px        — language chip
//   1fr          — accuracy bar + percent label
//   110px        — speed dot + label
//   170px        — action buttons (right-aligned)
//
// QML doesn't have fractional track sizes, so we use Layout.preferredWidth
// for fixed columns and Layout.fillWidth + Layout.minimumWidth + stretch
// weights (Layout.horizontalStretchFactor) for fluid columns. In Qt 6.5+
// GridLayout supports fractional-like behaviour via stretchFactors on
// RowLayout; we use RowLayout here since all cells are on one row.
Rectangle {
    id: root

    property string modelName: ""
    property string vendor: ""
    property string size: ""
    property string lang: ""
    property int accuracy: 0
    property string speed: ""
    property bool installed: false
    property bool active: false
    property bool lastRow: false

    signal rowClicked()
    signal activateClicked()
    signal installClicked()
    signal uninstallClicked()

    readonly property color hoverBg: Qt.rgba(244/255, 240/255, 232/255, 0.6)
    readonly property color activeBg: Qt.rgba(252/255, 242/255, 228/255, 0.4)

    implicitHeight: 64

    color: {
        if (active)   return activeBg
        if (hoverMa.containsMouse) return hoverBg
        return "transparent"
    }

    Behavior on color {
        ColorAnimation { duration: Theme.animFast }
    }

    // Bottom separator. Last row skips it (container's bottom radius
    // handles the clean edge).
    Rectangle {
        visible: !root.lastRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.borderSoft
    }

    MouseArea {
        id: hoverMa
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.rowClicked()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        spacing: 16

        // ── Name + vendor + optional "активна" chip ───────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.horizontalStretchFactor: 26
            Layout.minimumWidth: 260
            spacing: 10

            Rectangle {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                radius: 8
                color: root.installed ? Theme.accentWash : Theme.cardAlt
                border.width: 1
                border.color: root.installed ? Theme.accentSoft : Theme.border

                SvgIcon {
                    anchors.centerIn: parent
                    name: "cpu"
                    size: 15
                    strokeWidth: 1.7
                    color: root.installed ? Theme.accent : Theme.ink4
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: root.modelName
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }

                    Chip {
                        visible: root.active
                        tone: "accent"
                        text: "активна"
                    }

                    Item { Layout.fillWidth: true }
                }

                Text {
                    Layout.fillWidth: true
                    text: root.vendor
                    color: Theme.ink4
                    font.family: Theme.fontMono
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
            }
        }

        // ── Size ──────────────────────────────────────────────────
        Text {
            Layout.preferredWidth: 90
            text: root.size
            color: Theme.ink2
            font.family: Theme.fontMono
            font.pixelSize: 12
        }

        // ── Lang ──────────────────────────────────────────────────
        Item {
            Layout.preferredWidth: 80
            implicitHeight: langChip.implicitHeight

            Chip {
                id: langChip
                tone: "neutral"
                text: root.lang
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        // ── Accuracy bar + label ──────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.horizontalStretchFactor: 10
            Layout.minimumWidth: 100
            spacing: 8

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 4
                radius: 2
                color: Theme.borderSoft

                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: parent.width * (root.accuracy / 100.0)
                    radius: 2
                    color: root.accuracy > 95
                        ? Theme.green
                        : (root.accuracy > 90 ? Theme.accent : Theme.amber)
                }
            }

            Text {
                Layout.preferredWidth: 32
                horizontalAlignment: Text.AlignRight
                text: root.accuracy + "%"
                color: Theme.ink2
                font.family: Theme.fontMono
                font.pixelSize: 11
            }
        }

        // ── Speed ────────────────────────────────────────────────
        RowLayout {
            Layout.preferredWidth: 110
            spacing: 6

            Rectangle {
                Layout.preferredWidth: 7
                Layout.preferredHeight: 7
                radius: 7
                color: root.speed.indexOf("быстро") !== -1
                    ? Theme.green
                    : (root.speed === "медленно" ? Theme.amber : Theme.ink3)
            }

            Text {
                Layout.fillWidth: true
                text: root.speed
                color: Theme.ink2
                font.family: Theme.fontSans
                font.pixelSize: 12
                elide: Text.ElideRight
            }
        }

        // ── Action buttons (right-aligned) ────────────────────────
        RowLayout {
            Layout.preferredWidth: 170
            spacing: 6

            Item { Layout.fillWidth: true }

            // Installed, not active → "Сделать активной"
            SoftButton {
                visible: root.installed && !root.active
                sizeTag: "sm"
                text: "Сделать активной"
                onClicked: root.activateClicked()
            }

            // Installed → trash icon. Active row uses ghost-plain text
            // "Удалить" (per prototype); inactive installed gets just
            // the icon.
            GhostButton {
                visible: root.installed && root.active
                sizeTag: "sm"
                plain: true
                iconName: "trash"
                text: "Удалить"
                onClicked: root.uninstallClicked()
            }
            GhostButton {
                visible: root.installed && !root.active
                sizeTag: "sm"
                plain: true
                iconName: "trash"
                text: ""
                onClicked: root.uninstallClicked()
            }

            PrimaryButton {
                visible: !root.installed
                sizeTag: "sm"
                iconName: "download"
                text: "Установить"
                onClicked: root.installClicked()
            }
        }
    }
}
