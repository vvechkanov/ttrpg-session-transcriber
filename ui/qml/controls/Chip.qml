import QtQuick
import QtQuick.Layouts
import App.Theme

// Small status chip / badge. `tone` selects a palette:
//   accent  — active/primary marker
//   neutral — default language / metadata tag
//   green   — success
//   amber   — warning
//   red     — destructive
Rectangle {
    id: root

    property string tone: "neutral"
    property string text: ""
    property bool dot: false

    // Named `tones`, not `palette` — `palette` exists on Item and the
    // QML engine warns about shadowing it.
    readonly property var tones: ({
        accent:  { bg: Theme.accentWash, fg: Theme.accentDeep, bd: Theme.accentSoft, dot: Theme.accent },
        neutral: { bg: Theme.cardAlt,    fg: Theme.ink3,       bd: Theme.borderSoft, dot: Theme.ink4 },
        green:   { bg: Theme.greenSoft,  fg: Theme.green,      bd: Qt.rgba(0.35, 0.54, 0.24, 0.25), dot: Theme.green },
        amber:   { bg: "#F7E6C9",        fg: Theme.amber,      bd: "#EBD09A",        dot: Theme.amber },
        red:     { bg: Theme.redSoft,    fg: Theme.red,        bd: Qt.rgba(0.77, 0.28, 0.17, 0.25), dot: Theme.red }
    })

    readonly property var p: tones[tone] || tones.neutral

    implicitHeight: 20
    implicitWidth: row.implicitWidth + 16
    radius: Theme.radiusSm - 1
    color: p.bg
    border.width: 1
    border.color: p.bd

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 5

        Rectangle {
            visible: root.dot
            width: 5; height: 5; radius: 5
            color: root.p.dot
        }

        Text {
            text: root.text
            color: root.p.fg
            font.family: Theme.fontSans
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.letterSpacing: 0.2
        }
    }
}
