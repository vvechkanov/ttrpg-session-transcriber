// Lucide-style icons (same set the HTML prototype uses, same 24x24
// viewBox, same 1.5 stroke width). Each entry is a single SVG "d"
// string — multiple sub-paths are joined with a space, relying on the
// fact that `M` (moveto) resets the pen and starts a new subpath.
//
// Using one compound string per icon avoids the PathSvg/Repeater
// problem: QQuickShapePath.pathElements is typed `list<PathElement>`
// and does not accept a Repeater delegate — but it does accept a
// single PathSvg containing multiple subpaths.

.pragma library

var list =
    "M8 6 H21 M8 12 H21 M8 18 H21 " +
    "M3 6 H3.01 M3 12 H3.01 M3 18 H3.01";

var zap =
    "M13 2 L3 14 L12 14 L11 22 L21 10 L12 10 L13 2 Z";

// Gear: circle (two-arc expression, safer than the 0.001-trick) +
// outer body verbatim from Lucide's `settings` icon.
var settings =
    "M9 12 A3 3 0 1 0 15 12 A3 3 0 1 0 9 12 Z " +
    "M19.4 15 a1.65 1.65 0 0 0 .33 1.82 l.06 .06 " +
    "a2 2 0 1 1 -2.83 2.83 l-.06 -.06 " +
    "a1.65 1.65 0 0 0 -1.82 -.33 a1.65 1.65 0 0 0 -1 1.51 V21 " +
    "a2 2 0 0 1 -4 0 v-.09 " +
    "a1.65 1.65 0 0 0 -1 -1.51 a1.65 1.65 0 0 0 -1.82 .33 l-.06 .06 " +
    "a2 2 0 1 1 -2.83 -2.83 l.06 -.06 " +
    "a1.65 1.65 0 0 0 .33 -1.82 a1.65 1.65 0 0 0 -1.51 -1 H3 " +
    "a2 2 0 0 1 0 -4 h.09 " +
    "a1.65 1.65 0 0 0 1.51 -1 a1.65 1.65 0 0 0 -.33 -1.82 l-.06 -.06 " +
    "a2 2 0 1 1 2.83 -2.83 l.06 .06 " +
    "a1.65 1.65 0 0 0 1.82 .33 a1.65 1.65 0 0 0 1 -1.51 V3 " +
    "a2 2 0 0 1 4 0 v.09 " +
    "a1.65 1.65 0 0 0 1 1.51 a1.65 1.65 0 0 0 1.82 -.33 l.06 -.06 " +
    "a2 2 0 1 1 2.83 2.83 l-.06 .06 " +
    "a1.65 1.65 0 0 0 -.33 1.82 a1.65 1.65 0 0 0 1.51 1 H21 " +
    "a2 2 0 0 1 0 4 h-.09 " +
    "a1.65 1.65 0 0 0 -1.51 1 z";

function byName(name) {
    switch (name) {
        case "list":     return list;
        case "zap":      return zap;
        case "settings": return settings;
        default:         return "";
    }
}
