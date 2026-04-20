import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import App.Theme

// Primary action button: filled accent background with inner highlight
// and warm shadow. Mirrors the prototype's `Btn variant="primary"`.
//
// Size is a tag ("sm" | "md"), matching the prototype. Default is
// "md". The inner highlight is a 1px translucent top edge — achieved
// with a gradient, not a separate Rectangle, to keep the hit rect
// exactly on the button.
Button {
    id: root

    property string sizeTag: "md"
    property string iconName: ""

    topPadding: 0
    bottomPadding: 0
    leftPadding: sizeTag === "sm" ? 10 : 14
    rightPadding: sizeTag === "sm" ? 10 : 14
    implicitHeight: sizeTag === "sm" ? 28 : 36

    hoverEnabled: true
    // No overlaid pointer handler — see GhostButton for the write-up.

    contentItem: RowLayout {
        spacing: sizeTag === "sm" ? 6 : 8

        SvgIcon {
            visible: root.iconName.length > 0
            name: root.iconName
            size: root.sizeTag === "sm" ? 14 : 16
            color: Theme.accentFg
            strokeWidth: 1.7
        }

        Text {
            Layout.fillWidth: true
            text: root.text
            horizontalAlignment: Text.AlignHCenter
            color: Theme.accentFg
            font.family: Theme.fontSans
            font.pixelSize: root.sizeTag === "sm" ? 12 : 13
            font.weight: Font.DemiBold
        }
    }

    background: Rectangle {
        radius: Theme.radiusSm + 1
        border.width: 1
        border.color: Theme.accentDeep

        // Top-edge inset highlight via gradient (prototype uses
        // `inset 0 1px 0 rgba(255,255,255,0.22)`).
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.lighter(Theme.accent, 1.06) }
            GradientStop { position: 0.04; color: Theme.accent }
            GradientStop { position: 1.0; color: Theme.accent }
        }

        Rectangle {
            // Darker wash on hover / press
            anchors.fill: parent
            radius: parent.radius
            // No Behavior: a 140 ms ColorAnimation on hover/unhover
            // makes single-frame hovered toggles visible as a smooth
            // flash. Snap-change is indistinguishable from a static
            // hover tint and avoids the artefact.
            color: root.pressed
                ? Qt.rgba(0, 0, 0, 0.10)
                : (root.hovered ? Qt.rgba(0, 0, 0, 0.05) : "transparent")
        }

        opacity: root.enabled ? 1.0 : 0.5
    }
}
