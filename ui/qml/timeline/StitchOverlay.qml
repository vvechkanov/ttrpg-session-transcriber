import QtQuick
import App.Theme

// Vertical glow lines across all track lanes, shown during the merge
// phase. Each line marks where the merger is bridging a Craig gap
// with a chat-log event.
//
// Visual notes (from the prototype's MergeStitches):
//   • 1px wide, fades in from top and out at bottom via a gradient
//   • accent color with an 8px outer glow
//   • opacity pulses infinitely, staggered 200ms per marker
//
// Qt Quick doesn't have CSS box-shadow, so the glow is a faint second
// rectangle behind the main line. It reads as a halo at normal zoom.
Item {
    id: root

    // List of 0..100 positions (in timeline %) to draw lines at.
    property var stitches: []
    // Pixel offset of the tracks area from the left edge of this item,
    // accounting for the 220px gutter.
    property int gutterWidth: 220

    // Non-interactive: merge phase is display-only; clicks on the
    // tracks below should still reach them.
    // (No MouseArea here, so hit-testing falls through.)

    Repeater {
        model: root.stitches

        delegate: Item {
            readonly property real _pct: modelData
            // Position inside the tracks column, beyond the gutter.
            x: root.gutterWidth + (root.width - root.gutterWidth) * (_pct / 100.0)
            y: 0
            width: 1
            height: root.height

            // Outer halo
            Rectangle {
                x: -3
                y: 0
                width: 7
                height: parent.height
                opacity: 0.25

                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.2; color: Theme.accent }
                    GradientStop { position: 0.8; color: Theme.accent }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }

            // Core line
            Rectangle {
                x: 0
                y: 0
                width: 1
                height: parent.height

                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.2; color: Theme.accent }
                    GradientStop { position: 0.8; color: Theme.accent }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }

            // Staggered fade-in when the stitch first appears + infinite
            // pulse so the overlay reads as "being built".
            opacity: 0.0
            SequentialAnimation on opacity {
                running: true
                NumberAnimation { from: 0.0; to: 1.0; duration: Theme.animMed; easing.type: Easing.OutCubic }
                SequentialAnimation {
                    loops: Animation.Infinite
                    NumberAnimation { from: 1.0; to: 0.55; duration: 1000; easing.type: Easing.InOutQuad }
                    NumberAnimation { from: 0.55; to: 1.0; duration: 1000; easing.type: Easing.InOutQuad }
                }
            }
        }
    }
}
