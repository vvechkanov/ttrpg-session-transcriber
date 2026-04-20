import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// merged.txt output pill. Idle phase shows the "ожидает" neutral chip;
// once the pipeline finishes (phase == "done") this flips to an accent
// tint + a green size chip and reveals two action buttons — "Открыть"
// opens the file in the system text editor, "Открыть папку" opens the
// session folder in Explorer/Finder. Both are deferred to
// Qt.openUrlExternally so Qt picks up the OS default — no platform-
// specific subprocess calls, no QtCore.QDesktopServices binding dance.
Rectangle {
    id: root

    //: Display label — the bare file name, not the full path. The path
    //: travels separately in :pyattr:`PipelineController.outputPath`
    //: for the openers below.
    property string fileName: "merged.txt"

    //: Absolute path used by Qt.openUrlExternally. Empty until the
    //: merger emits done — buttons stay hidden in that case.
    property string outputPath: ""

    property bool done: false
    property string sizeCaption: "—"

    implicitHeight: 38
    implicitWidth: row.implicitWidth + 28
    radius: Theme.radiusSm + 2
    color: done ? Theme.accentWash : Theme.card
    border.width: 1
    border.color: done ? Theme.accentSoft : Theme.border

    // Compose a file:// URL from an OS path. Windows paths use
    // backslashes that QUrl needs converted to forward slashes;
    // POSIX paths pass through unchanged. Empty input returns an
    // empty URL so button click handlers no-op gracefully.
    function _fileUrl(path) {
        if (!path)
            return ""
        var normalised = path.replace(/\\/g, "/")
        return normalised.charAt(0) === "/" ? ("file://" + normalised)
                                            : ("file:///" + normalised)
    }

    function _folderUrl(path) {
        if (!path)
            return ""
        var slash = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"))
        if (slash <= 0)
            return ""
        return _fileUrl(path.substring(0, slash))
    }

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

        GhostButton {
            visible: root.done && root.outputPath.length > 0
            sizeTag: "sm"
            text: "Открыть"
            iconName: "externalLink"
            onClicked: Qt.openUrlExternally(root._fileUrl(root.outputPath))
        }

        GhostButton {
            visible: root.done && root.outputPath.length > 0
            sizeTag: "sm"
            text: "Открыть папку"
            iconName: "folderOpen"
            onClicked: Qt.openUrlExternally(root._folderUrl(root.outputPath))
        }
    }
}
