import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import App.Theme

// Soft button: filled cardAlt background with soft border. Used for
// inline actions in list rows (e.g. "Сделать активной").
Button {
    id: root

    property string sizeTag: "sm"
    property string iconName: ""

    topPadding: 0
    bottomPadding: 0
    leftPadding: sizeTag === "sm" ? 10 : 14
    rightPadding: sizeTag === "sm" ? 10 : 14
    implicitHeight: sizeTag === "sm" ? 28 : 36

    hoverEnabled: true
    // No overlaid pointer handler — see GhostButton for the write-up.

    contentItem: RowLayout {
        spacing: 6

        SvgIcon {
            visible: root.iconName.length > 0
            name: root.iconName
            size: 14
            color: Theme.ink2
            strokeWidth: 1.6
        }

        Text {
            Layout.fillWidth: true
            text: root.text
            horizontalAlignment: Text.AlignHCenter
            color: Theme.ink2
            font.family: Theme.fontSans
            font.pixelSize: root.sizeTag === "sm" ? 12 : 13
            font.weight: Font.Medium
        }
    }

    background: Rectangle {
        radius: Theme.radiusSm + 1
        border.width: 1
        border.color: Theme.borderSoft
        // No Behavior on color — see PrimaryButton for the rationale.
        color: root.pressed
            ? Theme.hover
            : (root.hovered ? Qt.darker(Theme.cardAlt, 1.02) : Theme.cardAlt)
        opacity: root.enabled ? 1.0 : 0.5
    }
}
