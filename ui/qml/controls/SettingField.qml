import QtQuick
import QtQuick.Layouts
import App.Theme

// Label + control pair. Mirrors the prototype's <Field>. Content is
// placed below the label; optional hint text appears beneath.
ColumnLayout {
    id: root

    property string label: ""
    property string hint: ""
    default property alias content: inner.data

    // То же, что `soon` у SettingsGroup, но для одного поля: настройка
    // без читателя, живущая внутри работающей группы.
    property bool soon: false
    // Осторожно: `enabled`, выставленный на месте вызова, перебивает
    // `enabled: !soon` отсюда. Сегодня это никому не мешает (поля
    // чанкера гасятся своим условием и `soon` не ставят), но
    // `soon: true` вместе со своим `enabled` тихо не сработает.

    Layout.fillWidth: true
    spacing: 6
    enabled: !soon

    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        Text {
            text: root.label
            color: Theme.ink3
            font.family: Theme.fontSans
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.letterSpacing: 0.6
            // Uppercase matches the prototype's `textTransform: 'uppercase'`.
            // We set the text itself uppercase in the caller rather than via
            // Qt's font.capitalization — keeps letter-spacing predictable.
        }

        Chip {
            visible: root.soon
            tone: "amber"
            text: "СКОРО"
        }

        // Только под плашку: видимая всегда, она добавляла 8px к
        // ширине каждого поля, включая рабочие.
        Item { visible: root.soon; Layout.fillWidth: true }
    }

    ColumnLayout {
        id: inner
        Layout.fillWidth: true
        spacing: 2
        opacity: root.soon ? 0.5 : 1.0
    }

    Text {
        visible: root.hint.length > 0
        text: root.hint
        color: Theme.ink4
        font.family: Theme.fontSans
        font.pixelSize: 10
    }
}
