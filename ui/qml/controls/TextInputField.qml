import QtQuick
import QtQuick.Controls.Basic
import App.Theme

// Text input with our warm card-on-bg styling. Mirrors the prototype's
// <TextInput> — 1px border in Theme.border, hover lightens to borderSoft,
// focus switches to accent. Defaults to the Sans stack; pass
// `mono: true` to swap for JetBrains-Mono (path fields, technical values).
TextField {
    id: root

    property bool mono: false

    leftPadding: 12
    rightPadding: 12
    topPadding: 8
    bottomPadding: 8

    implicitHeight: 34

    color: Theme.ink
    selectionColor: Theme.accentSoft
    selectedTextColor: Theme.ink

    font.family: mono ? Theme.fontMono : Theme.fontSans
    font.pixelSize: mono ? 12 : 13

    placeholderTextColor: Theme.ink4

    background: Rectangle {
        radius: Theme.radiusSm + 1
        color: Theme.card
        border.width: 1
        border.color: root.activeFocus
            ? Theme.accent
            : (root.hovered ? Theme.border : Theme.border)

        Behavior on border.color {
            ColorAnimation { duration: Theme.animFast }
        }
    }
}
