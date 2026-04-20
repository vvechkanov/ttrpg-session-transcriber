import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// Clickable pill showing the current default ASR engine (model name +
// precision + device). Click opens the model picker — the picker
// popover itself arrives with the TrackOverridePopover step.
Rectangle {
    id: root

    // The caller can override for testing. In the app, we leave these
    // blank so the bindings below pull the active backend's name + disk
    // size from ``ModelRegistry`` — whatever the user selects on the
    // Models screen is immediately reflected here without an extra wire.
    property string modelName: ""
    property string qualifier: ""

    // Resolve name + qualifier from ModelRegistry when not overridden.
    // ``entryForActive`` walks the rows for the one flagged active; if
    // none is installed yet we render a neutral "— · CPU" pill so the
    // user isn't lied to about which engine is running.
    function _entryForActive() {
        if (typeof modelRegistry === "undefined" || !modelRegistry) return null
        for (var i = 0; i < modelRegistry.rowCount(); i++) {
            var entry = modelRegistry.entryAt(i)
            if (entry && entry.active) return entry
        }
        return null
    }
    readonly property var _activeEntry: {
        // Re-evaluate when ModelRegistry changes its active row.
        if (typeof modelRegistry !== "undefined" && modelRegistry)
            modelRegistry.activeModelId
        return _entryForActive()
    }
    readonly property string _effectiveName: modelName.length > 0
        ? modelName
        : (_activeEntry ? _activeEntry.name : "—")
    readonly property string _effectiveQualifier: qualifier.length > 0
        ? qualifier
        : (_activeEntry ? (_activeEntry.size + " · CPU") : "CPU")

    signal clicked()

    implicitHeight: 32
    implicitWidth: row.implicitWidth + 24
    radius: Theme.radiusSm + 2
    color: hoverMa.containsMouse ? Theme.cardAlt : Theme.card
    border.width: 1
    border.color: Theme.border

    Behavior on color { ColorAnimation { duration: Theme.animFast } }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 10
        spacing: 10

        SvgIcon {
            name: "zap"; size: 14
            color: Theme.accent
            strokeWidth: 1.8
        }

        RowLayout {
            spacing: 4
            Text {
                text: root._effectiveName
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.weight: Font.DemiBold
                font.letterSpacing: -0.05
            }
            Text {
                text: "· " + root._effectiveQualifier
                color: Theme.ink4
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.weight: Font.Normal
            }
        }

        SvgIcon {
            name: "chevDown"; size: 12
            color: Theme.inkFaint
            strokeWidth: 1.7
        }
    }

    MouseArea {
        id: hoverMa
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
