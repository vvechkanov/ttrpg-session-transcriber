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

    Layout.fillWidth: true
    spacing: 6

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

    ColumnLayout {
        id: inner
        Layout.fillWidth: true
        spacing: 2
    }

    Text {
        visible: root.hint.length > 0
        text: root.hint
        color: Theme.ink4
        font.family: Theme.fontSans
        font.pixelSize: 10
    }
}
