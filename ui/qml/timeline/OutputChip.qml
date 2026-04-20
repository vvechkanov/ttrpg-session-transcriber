import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// merged.txt output pill. Idle phase shows the "ожидает" neutral chip;
// once the pipeline finishes (phase == "done") this flips to an accent
// tint + a green "84 KB" chip. Only the idle variant renders for now.
Rectangle {
    id: root

    property string fileName: "merged.txt"
    property bool done: false
    property string sizeCaption: "84 KB"

    implicitHeight: 38
    implicitWidth: row.implicitWidth + 28
    radius: Theme.radiusSm + 2
    color: done ? Theme.accentWash : Theme.card
    border.width: 1
    border.color: done ? Theme.accentSoft : Theme.border

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 10
        spacing: 10

        SvgIcon {
            name: "file"; size: 14
            color: root.done ? Theme.accent : Theme.ink3
            strokeWidth: 1.7
        }

        Text {
            text: root.fileName
            color: Theme.ink
            font.family: Theme.fontMono
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }

        // Right-side status chip
        Chip {
            tone: root.done ? "green" : "neutral"
            text: root.done ? root.sizeCaption : "ожидает"
            dot: root.done
        }
    }
}
