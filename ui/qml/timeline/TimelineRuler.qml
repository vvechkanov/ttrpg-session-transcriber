import QtQuick
import QtQuick.Shapes
import App.Theme
import "../controls"

// Ruler strip: 30-minute tick marks (major every hour, minor every
// half-hour), mono labels at majors, and a scissors-badged dashed line
// at the Craig segment split.
//
// Positions are computed from `totalMinutes` and `segmentSplitPct` so
// the widget is reusable for any session length.
Item {
    id: root

    // Defaults are zero — the ruler renders empty until the host
    // assigns real session metadata. Hardcoded mock durations used
    // to live here to make the prototype look alive; they confused
    // debugging because the ruler carried on showing "3h 47m" even
    // on a just-opened empty shell.
    property int totalMinutes: 0
    property real segmentSplitPct: 0.0

    // Minutes past midnight at the left edge, in the session's own
    // timezone. Labels are wall-clock because the window no longer
    // starts with the recording: on a session where Record was pressed
    // late, "0:00" would have to mean two different instants on the
    // same screen — the start of the chat and the start of the audio.
    // A clock reads the same everywhere, and matches the times the user
    // sees in the Foundry log next to it.
    property int clockStartMinutes: -1
    readonly property bool _wallClock: clockStartMinutes >= 0

    // Where the recording begins, 0..100 of the ruler. Everything left
    // of it is material with no audio behind it. ``hasTimeBefore``
    // is passed separately rather than derived from ``> 0`` so the
    // "is there anything before the recording" question is answered in
    // one place — Python — instead of twice here.
    property real recordingStartPct: 0.0
    property bool hasTimeBefore: false

    implicitHeight: 22

    // Skip tick-mark and split-marker rendering when the session
    // has no known duration. Avoids the degenerate Repeater run
    // (model = 1) that used to paint a single tick at x=0.
    readonly property bool _hasDuration: totalMinutes > 0

    // Everything before the recording started — the stretch of session
    // that has chat and dice but no sound. Hatch-free, just a wash, so
    // it reads as "outside" without competing with the tick marks.
    Rectangle {
        visible: root.hasTimeBefore
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        x: 0
        width: root.width * (root.recordingStartPct / 100.0)
        color: Qt.rgba(0, 0, 0, 0.035)
    }

    // The moment Record was pressed.
    Rectangle {
        visible: root.hasTimeBefore
        x: root.width * (root.recordingStartPct / 100.0)
        y: 0
        width: 1
        height: root.height
        color: Theme.amber
        opacity: 0.75
    }

    // Thin bottom separator.
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.borderSoft
    }

    // In wall-clock mode ticks land on real half-hours rather than on
    // multiples of 30 minutes from an arbitrary left edge — a session
    // starting at 18:55 should be labelled 19:00, 20:00, not 18:55,
    // 19:55.
    readonly property int _firstTick: _wallClock
        ? (30 - (clockStartMinutes % 30)) % 30
        : 0

    // Tick marks
    Repeater {
        model: root._hasDuration
               ? Math.floor((root.totalMinutes - root._firstTick) / 30) + 1
               : 0

        delegate: Item {
            readonly property int minute: root._firstTick + index * 30
            readonly property bool major: root._wallClock
                ? ((root.clockStartMinutes + minute) % 60) === 0
                : (minute % 60) === 0
            readonly property real pct: (minute / root.totalMinutes)

            x: root.width * pct
            y: 0
            width: 1
            height: root.height

            Rectangle {
                x: -0.5
                y: 0
                width: 1
                height: parent.major ? 8 : 4
                color: Theme.border
            }

            Text {
                visible: parent.major
                x: 4
                y: 9
                text: {
                    if (!root._wallClock)
                        return Math.floor(parent.minute / 60) + ":"
                             + (parent.minute % 60).toString().padStart(2, "0")
                    const abs = (root.clockStartMinutes + parent.minute) % 1440
                    return Math.floor(abs / 60).toString().padStart(2, "0")
                         + ":" + (abs % 60).toString().padStart(2, "0")
                }
                color: Theme.ink4
                font.family: Theme.fontMono
                font.pixelSize: 10
            }
        }
    }

    // Segment split — vertical dashed line with a scissors badge.
    Item {
        id: splitMark
        visible: root._hasDuration && root.segmentSplitPct > 0
        x: root.width * (root.segmentSplitPct / 100.0)
        y: 0
        width: 0
        height: root.height

        // Dashed vertical line rendered via Shape (Qt Quick Rectangle
        // borders don't support dashes).
        Shape {
            anchors.fill: parent
            layer.enabled: true
            layer.samples: 4

            ShapePath {
                strokeColor: Theme.border
                strokeWidth: 1
                fillColor: "transparent"
                strokeStyle: ShapePath.DashLine
                dashPattern: [3, 3]
                startX: 0; startY: 0
                PathLine { x: 0; y: splitMark.height }
            }
        }

        // Scissors badge anchored over the line.
        Rectangle {
            x: -8
            y: -4
            width: 16
            height: 16
            radius: 999
            color: Theme.card
            border.width: 1
            border.color: Theme.border

            SvgIcon {
                anchors.centerIn: parent
                name: "scissors"; size: 9
                color: Theme.ink4
                strokeWidth: 1.8
            }
        }
    }
}
