import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Clickable pill showing the current default ASR engine (model name +
// precision + device). Click opens the model picker — the picker
// popover itself arrives with the TrackOverridePopover step.
Rectangle {
    id: root

    // Strings for this slice. Real values come from ModelRegistry
    // and device selection once those are wired.
    property string modelName: "GigaAM-v3 RNNT"
    property string qualifier: "int8 · CPU"

    signal clicked()

    implicitHeight: 32
    implicitWidth: row.implicitWidth + 24
    radius: Theme.radiusSm + 2
    color: hoverMa.containsMouse ? Theme.cardAlt : Theme.card
    border.width: 1
    border.color: Theme.border

    Behavior on color { ColorAnimation { duration: Theme.animFast } }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 10
        spacing: 10

        SvgIcon {
            name: "zap"; size: 14
            color: Theme.accent
            strokeWidth: 1.8
        }

        RowLayout {
            spacing: 4
            Text {
                text: root.modelName
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.weight: Font.DemiBold
                font.letterSpacing: -0.05
            }
            Text {
                text: "· " + root.qualifier
                color: Theme.ink4
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.weight: Font.Normal
            }
        }

        SvgIcon {
            name: "chevDown"; size: 12
            color: Theme.inkFaint
            strokeWidth: 1.7
        }
    }

    MouseArea {
        id: hoverMa
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
