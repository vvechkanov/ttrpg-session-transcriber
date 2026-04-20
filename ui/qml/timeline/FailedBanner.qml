import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Error banner shown when phase === "failed".
//
// Mirrors DoneSummary's layout so the two states feel paired — same
// round icon on the left, headline + detail on the right — but with a
// red wash instead of green. The "Retry" action re-enters the pipeline
// by firing ``runClicked``; a ghost "Скрыть" clears AppModel's error
// string and hides the banner without touching phase.
Rectangle {
    id: root
    objectName: "failedBanner"

    property string message: ""

    signal retryClicked()
    signal dismissClicked()

    Layout.fillWidth: true
    implicitHeight: row.implicitHeight + 32
    radius: Theme.radiusLg
    border.width: 1
    border.color: Theme.redSoft

    gradient: Gradient {
        orientation: Gradient.Horizontal
        GradientStop { position: 0.0; color: Theme.redSoft }
        GradientStop { position: 0.6; color: Theme.card }
    }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 16
        spacing: 14

        Rectangle {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            radius: 12
            color: Theme.card
            border.width: 1
            border.color: Theme.redSoft

            SvgIcon {
                anchors.centerIn: parent
                name: "alert"; size: 20
                color: Theme.red
                strokeWidth: 2.2
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3

            Text {
                Layout.fillWidth: true
                text: "Обработка прервана"
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
            sizeTag: "sm"
            plain: true
            text: "Скрыть"
            onClicked: root.dismissClicked()
        }

        PrimaryButton {
            sizeTag: "sm"
            iconName: "refresh"
            text: "Повторить"
            onClicked: root.retryClicked()
        }
    }
}
