import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Warning shown when the Craig recording does not cover the whole
// session — someone hit Record late, so part of the Foundry chat and
// possibly a whole encounter have no audio behind them.
//
// Deliberately *not* a FailedBanner clone in red: nothing failed and
// there is nothing to retry. The material is simply gone, and the only
// useful response is knowing about it before spending an hour on ASR.
// Hence amber, no action buttons, and a single "Скрыть".
Rectangle {
    id: root
    objectName: "coverageBanner"

    property string message: ""

    signal dismissClicked()

    Layout.fillWidth: true
    implicitHeight: row.implicitHeight + 32
    radius: Theme.radiusLg
    border.width: 1
    border.color: Theme.amber
    // Flat card, not FailedBanner's coloured wash: this is a notice, not
    // an alarm. The amber lives in the border and the icon.
    color: Theme.card

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 16
        spacing: 14

        Rectangle {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            Layout.alignment: Qt.AlignTop
            radius: 12
            color: Theme.card
            border.width: 1
            border.color: Theme.amber

            SvgIcon {
                anchors.centerIn: parent
                name: "alert"; size: 20
                color: Theme.amber
                strokeWidth: 2.2
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3

            Text {
                Layout.fillWidth: true
                text: "Запись покрывает не всю сессию"
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 15
                font.weight: Font.Bold
                font.letterSpacing: -0.2
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                visible: root.message.length > 0
                text: root.message
                color: Theme.ink3
                font.family: Theme.fontMono
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }

        GhostButton {
            Layout.alignment: Qt.AlignTop
            sizeTag: "sm"
            plain: true
            text: "Скрыть"
            onClicked: root.dismissClicked()
        }
    }
}
