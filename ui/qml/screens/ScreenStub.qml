import QtQuick
import QtQuick.Layouts
import App.Theme

// Placeholder for screens not yet implemented. Renders a centered title
// + subtitle on the app background so navigation can be exercised end-
// to-end while the real screens are being built.
//
// Remove when every real screen replaces its stub.
Rectangle {
    id: root
    color: Theme.bg

    property string title: ""
    property string subtitle: ""

    ColumnLayout {
        anchors.centerIn: parent
        spacing: Theme.space2

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: root.title
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: Theme.fontH1
            font.weight: Font.DemiBold
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: root.subtitle
            color: Theme.ink3
            font.family: Theme.fontSans
            font.pixelSize: Theme.fontBody
        }
    }
}
