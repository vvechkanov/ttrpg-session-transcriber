import QtQuick
import QtQuick.Shapes
import "Icons.js" as Icons

// Lucide-style SVG icon renderer.
//
// The prototype uses inline SVGs on a 24x24 viewBox with stroke 1.5 and
// round caps/joins. We mirror that with Shape + ShapePath. Icons are
// looked up by name in controls/Icons.js (see Icons.byName).
//
// Example:
//     SvgIcon { name: "list"; color: Theme.ink2; size: 14 }
Item {
    id: root

    property string name: ""
    property color color: "#000000"
    property int size: 16
    property real strokeWidth: 1.5

    implicitWidth: size
    implicitHeight: size

    Shape {
        id: shape
        anchors.fill: parent
        // Keep visual stroke width constant by compensating for the
        // 24 → size scale applied via the transform below.
        layer.enabled: true
        layer.samples: 4

        transform: Scale {
            xScale: root.size / 24.0
            yScale: root.size / 24.0
        }

        ShapePath {
            strokeColor: root.color
            strokeWidth: root.strokeWidth * 24.0 / Math.max(root.size, 1)
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin

            // Icons.js emits one compound `d` string per icon — multi-
            // stroke icons use space-separated `M...` subpaths, which
            // is valid SVG and avoids pathElements list-typing issues.
            PathSvg { path: Icons.byName(root.name) }
        }
    }
}
