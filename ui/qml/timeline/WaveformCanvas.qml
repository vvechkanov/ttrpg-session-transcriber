import QtQuick
import QtQuick.Layouts
import App.Theme

// Waveform with a phase-driven fill overlay.
//
// Peaks come from core.peaks.get_or_compute_peaks via PeaksWorker on
// a background QThread — an ffmpeg-decoded max(abs(x)) reduction
// cached as <audio>.peaks.bin. An empty peaks list renders an empty
// lane (used before extraction finishes on ingest).
//
// Two passes:
//   1. `baseColor` — every bar at the "dry" muted grey.
//   2. `fillColor` — the first `progress * N` bars on top, tinted.
//
// The caller picks the fill colour by per-track status (accent for
// normal ASR, green for cached, purple for whisper-override, redSoft
// for failed) via the `fillColor` prop.
Item {
    id: root

    property var peaks: []            // list<real>
    property bool muted: false        // listener — draws at lower alpha
    property real progress: 0.0       // 0..1
    property color fillColor: Theme.accent

    readonly property color baseColor: muted
        ? Qt.rgba(148/255, 137/255, 126/255, 0.15)
        : Qt.rgba(107/255, 98/255, 90/255, 0.16)

    readonly property real _minHeight: 2
    readonly property real _padX: 2
    readonly property real _gap: 1.5

    Row {
        anchors.fill: parent
        anchors.leftMargin: root._padX
        anchors.rightMargin: root._padX
        spacing: root._gap

        Repeater {
            model: root.peaks

            delegate: Item {
                width: (root.width - 2 * root._padX
                        - root._gap * (root.peaks.length - 1))
                       / Math.max(root.peaks.length, 1)
                height: root.height

                // Phase-fill tint decision for this bar:
                //   fraction of this bar's left edge ≤ progress → use
                //   `fillColor`; otherwise `baseColor`.
                readonly property real _barFrac:
                    index / Math.max(root.peaks.length, 1)
                readonly property bool _isFilled: _barFrac < root.progress

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width
                    height: Math.max(
                        root._minHeight,
                        (modelData * 0.8 + 0.15) * root.height
                    )
                    radius: 1.5
                    color: parent._isFilled ? root.fillColor : root.baseColor

                    Behavior on color {
                        ColorAnimation { duration: 220 }
                    }
                }
            }
        }
    }
}
