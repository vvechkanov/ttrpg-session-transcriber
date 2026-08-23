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

    // Группа объявлена, но за ней нет ни одного читателя настройки:
    // значение ложится в QSettings и никем не используется. Такую
    // группу выключаем и помечаем «скоро» — молча принимать ввод в
    // никуда хуже, чем не показывать контрол вовсе.
    property bool soon: false
    // Осторожно: `enabled`, выставленный на месте вызова, перебивает
    // `enabled: !soon` отсюда. Сегодня это никому не мешает (поля
    // чанкера гасятся своим условием и `soon` не ставят), но
    // `soon: true` вместе со своим `enabled` тихо не сработает.

    Layout.fillWidth: true
    Layout.bottomMargin: 16
    enabled: !soon
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

        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: root.description.length > 0 ? 2 : 12
            spacing: 8

            Text {
                text: root.title
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 14
                font.weight: Font.Bold
                font.letterSpacing: -0.2
            }

            Chip {
                visible: root.soon
                tone: "amber"
                text: "СКОРО"
            }

            // Только под плашку: видимая всегда, она добавляла
            // 8px к ширине каждого поля, включая рабочие.
            Item { visible: root.soon; Layout.fillWidth: true }
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
            // Приглушаем только содержимое: заголовок с пометкой должен
            // оставаться читаемым, иначе «скоро» тонет вместе с ним.
            opacity: root.soon ? 0.5 : 1.0
        }
    }
}
