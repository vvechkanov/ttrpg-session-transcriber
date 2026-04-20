import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import App.Theme

// Ghost button: transparent background with a subtle border.
// If `plain` is true, the border is also transparent (prototype's
// `variant="ghostPlain"`).
//
// `danger` tints text red and uses the red-soft border.
Button {
    id: root

    property string sizeTag: "md"
    property string iconName: ""
    property bool plain: false
    property bool danger: false

    topPadding: 0
    bottomPadding: 0
    leftPadding: sizeTag === "sm" ? 10 : 14
    rightPadding: sizeTag === "sm" ? 10 : 14
    implicitHeight: sizeTag === "sm" ? 28 : 36

    hoverEnabled: true

    HoverHandler {
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    readonly property color textColor: danger ? Theme.red : Theme.ink2
    readonly property color borderColor: danger
        ? Theme.redSoft
        : (plain ? "transparent" : Theme.border)

    contentItem: RowLayout {
        spacing: root.sizeTag === "sm" ? 6 : 8

        SvgIcon {
            visible: root.iconName.length > 0
            name: root.iconName
            size: root.sizeTag === "sm" ? 14 : 16
            color: root.textColor
            strokeWidth: 1.6
        }

        Text {
            Layout.fillWidth: true
            text: root.text
            horizontalAlignment: Text.AlignHCenter
            color: root.textColor
            font.family: Theme.fontSans
            font.pixelSize: root.sizeTag === "sm" ? 12 : 13
            font.weight: Font.Medium
            visible: root.text.length > 0
        }
    }

    background: Rectangle {
        radius: Theme.radiusSm + 1
        border.width: 1
        border.color: root.borderColor
        color: root.pressed
            ? Theme.cardAlt
            : (root.hovered ? Theme.hover : "transparent")

        Behavior on color {
            ColorAnimation { duration: Theme.animFast }
        }

        opacity: root.enabled ? 1.0 : 0.5
    }
}
