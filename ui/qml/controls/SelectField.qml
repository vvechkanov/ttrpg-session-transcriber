import QtQuick
import QtQuick.Controls.Basic
import App.Theme

// Dropdown select styled to match TextInputField. Takes the same
// visual geometry so forms using both line up cleanly.
//
// `model` is a QtObject list like [{ v: "ru", l: "Русский" }, ...] —
// the "v" is the stored value, "l" is the label shown to the user.
ComboBox {
    id: root

    textRole: "l"
    valueRole: "v"

    implicitHeight: 34
    leftPadding: 12
    rightPadding: 36
    topPadding: 0
    bottomPadding: 0

    font.family: Theme.fontSans
    font.pixelSize: 13

    background: Rectangle {
        radius: Theme.radiusSm + 1
        color: Theme.card
        border.width: 1
        border.color: root.activeFocus ? Theme.accent : Theme.border
        Behavior on border.color { ColorAnimation { duration: Theme.animFast } }
    }

    contentItem: Text {
        leftPadding: 0
        rightPadding: 0
        verticalAlignment: Text.AlignVCenter
        text: root.displayText
        color: Theme.ink2
        font: root.font
        elide: Text.ElideRight
    }

    indicator: SvgIcon {
        x: root.width - width - 10
        y: (root.height - height) / 2
        name: "chevDown"
        size: 14
        color: Theme.ink3
        strokeWidth: 1.7
    }

    delegate: ItemDelegate {
        width: root.width
        height: 30
        padding: 0

        contentItem: Text {
            leftPadding: 12
            rightPadding: 12
            verticalAlignment: Text.AlignVCenter
            text: modelData.l !== undefined ? modelData.l : modelData
            color: Theme.ink2
            font.family: Theme.fontSans
            font.pixelSize: 13
        }

        background: Rectangle {
            color: parent.highlighted ? Theme.accentWash : "transparent"
        }
    }

    popup: Popup {
        y: root.height + 2
        width: root.width
        implicitHeight: contentItem.implicitHeight + 8
        padding: 4

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
        }

        background: Rectangle {
            radius: Theme.radiusSm + 1
            color: Theme.card
            border.width: 1
            border.color: Theme.border
        }
    }
}
