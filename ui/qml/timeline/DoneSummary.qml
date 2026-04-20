import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Celebratory banner shown on the done phase.
//
// Green-tinted 135° gradient, card-framed check icon on the left, big
// headline ("Готово за 14 минут 23 секунды"), mono secondary stats
// line. Static — re-rendering is cheap, there's nothing animated
// here beyond the Rectangle.
Rectangle {
    id: root

    property string durationLabel: ""
    property string statsLine: ""

    Layout.fillWidth: true
    implicitHeight: row.implicitHeight + 36
    radius: Theme.radiusLg
    border.width: 1
    border.color: Theme.greenSoft

    gradient: Gradient {
        orientation: Gradient.Horizontal
        GradientStop { position: 0.0; color: Theme.greenSoft }
        GradientStop { position: 0.6; color: Theme.card }
    }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        Rectangle {
            Layout.preferredWidth: 44
            Layout.preferredHeight: 44
            radius: 12
            color: Theme.card
            border.width: 1
            border.color: Theme.greenSoft

            SvgIcon {
                anchors.centerIn: parent
                name: "check"; size: 22
                color: Theme.green
                strokeWidth: 2.2
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3

            Text {
                Layout.fillWidth: true
                text: root.durationLabel
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 18
                font.weight: Font.Bold
                font.letterSpacing: -0.3
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: root.statsLine
                color: Theme.ink3
                font.family: Theme.fontMono
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
        }
    }
}
