import QtQuick
import QtQuick.Layouts
import App.Theme

// Card-shaped container for one section on the Settings screen.
// Title + optional description + arbitrary content. Matches the
// prototype's <SettingGroup>.
Rectangle {
    id: root

    property string title: ""
    property string description: ""
    default property alias content: inner.data

    Layout.fillWidth: true
    Layout.bottomMargin: 16
    radius: Theme.radiusLg
    color: Theme.card
    border.width: 1
    border.color: Theme.border
    implicitHeight: column.implicitHeight + 40

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: 20
        spacing: 0

        Text {
            Layout.fillWidth: true
            Layout.bottomMargin: root.description.length > 0 ? 2 : 12
            text: root.title
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: 14
            font.weight: Font.Bold
            font.letterSpacing: -0.2
        }

        Text {
            visible: root.description.length > 0
            Layout.fillWidth: true
            Layout.bottomMargin: 12
            text: root.description
            color: Theme.ink3
            font.family: Theme.fontSans
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }

        ColumnLayout {
            id: inner
            Layout.fillWidth: true
            spacing: 12
        }
    }
}
