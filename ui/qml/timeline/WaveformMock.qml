import QtQuick
import QtQuick.Layouts
import App.Theme

// Mock waveform: renders a list of 0..1 peak values as a row of
// rounded bars. Idle phase draws all bars in the muted "dry" colour —
// the filled / progress overlay arrives when the ASR phase is wired.
//
// Listener tracks render with an even lighter grey (see `muted`).
Item {
    id: root

    property var peaks: []        // list<real>
    property bool muted: false    // listener tracks
    property color barColor: muted
        ? Qt.rgba(148/255, 137/255, 126/255, 0.15)
        : Qt.rgba(107/255, 98/255, 90/255, 0.16)

    // Minimum drawn bar height, keeps silence zones visible.
    readonly property real _minHeight: 2
    readonly property real _padX: 2
    readonly property real _gap: 1.5

    Row {
        anchors.fill: parent
        anchors.leftMargin: root._padX
        anchors.rightMargin: root._padX
        anchors.topMargin: 0
        anchors.bottomMargin: 0
        spacing: root._gap

        Repeater {
            model: root.peaks

            delegate: Item {
                width: (root.width - 2 * root._padX
                        - root._gap * (root.peaks.length - 1))
                       / Math.max(root.peaks.length, 1)
                height: root.height

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    // `modelData` is the per-bar 0..1 peak.
                    height: Math.max(
                        root._minHeight,
                        (modelData * 0.8 + 0.15) * root.height
                    )
                    width: parent.width
                    radius: 1.5
                    color: root.barColor
                }
            }
        }
    }
}
