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

var plus     = "M12 5 V19 M5 12 H19";
var xmark    = "M18 6 L6 18 M6 6 L18 18";
var check    = "M20 6 L9 17 L4 12";
var search   = "M10 17 A7 7 0 1 0 10 3 A7 7 0 1 0 10 17 Z M20 20 L15.65 15.65";
var download = "M21 15 V19 A2 2 0 0 1 19 21 H5 A2 2 0 0 1 3 19 V15 " +
               "M7 10 L12 15 L17 10 " +
               "M12 15 V3";
var trash    = "M3 6 H21 " +
               "M19 6 L18 20 A2 2 0 0 1 16 22 H8 A2 2 0 0 1 6 20 L5 6 " +
               "M10 11 V17 M14 11 V17";
var folder   = "M22 19 A2 2 0 0 1 20 21 H4 A2 2 0 0 1 2 19 V5 A2 2 0 0 1 4 3 H9 L11 6 H20 A2 2 0 0 1 22 8 Z";
// Minimal CPU-ish glyph. Lucide's `cpu` has lots of leg-lines — drawn
// here as the central square plus the inner processor.
var cpu      = "M4 4 H20 V20 H4 Z " +
               "M9 9 H15 V15 H9 Z " +
               "M9 1 V4 M15 1 V4 " +
               "M9 20 V23 M15 20 V23 " +
               "M20 9 H23 M20 15 H23 " +
               "M1 9 H4 M1 15 H4";
// Storage box (Lucide `box`). Top arrow then body.
var box      = "M21 8 V21 H3 V8 " +
               "M1 3 H23 V8 H1 Z " +
               "M10 12 H14";

var folderOpen = "M6 14 L7.5 11.1 A2 2 0 0 1 9.24 10 H20 A2 2 0 0 1 21.94 12.5 L20.4 18.5 A2 2 0 0 1 18.45 20 H4 A2 2 0 0 1 2 18 V5 A2 2 0 0 1 4 3 H7.9 A2 2 0 0 1 9.59 3.9 L10.4 5.1 A2 2 0 0 0 12.07 6 H18 A2 2 0 0 1 20 8 V10";

// Info: outline circle + "i" body (line + dot).
var info = "M12 2 A10 10 0 1 0 12 22 A10 10 0 1 0 12 2 Z " +
           "M12 12 V16 " +
           "M12 8 H12.01";

var chevRight = "M9 6 L15 12 L9 18";
var chevDown  = "M6 9 L12 15 L18 9";

var scissors = "M6 6 m-3 0 a3 3 0 1 0 6 0 a3 3 0 1 0 -6 0 Z " +
               "M6 18 m-3 0 a3 3 0 1 0 6 0 a3 3 0 1 0 -6 0 Z " +
               "M20 4 L8.12 15.88 " +
               "M14.47 14.48 L20 20 " +
               "M8.12 8.12 L12 12";

var chat = "M21 15 A2 2 0 0 1 19 17 H7 L3 21 V5 A2 2 0 0 1 5 3 H19 A2 2 0 0 1 21 5 Z";

// Lucide "swords" simplified — crossed strokes read as weapons at
// small sizes.
var swords = "M14.5 17.5 L3 6 V3 H6 L17.5 14.5 " +
             "M13 19 L19 13 " +
             "M16 16 L20 20 " +
             "M19 21 L21 19 " +
             "M14.5 6.5 L18 3 H21 V6 L17.5 9.5 " +
             "M5 14 L9 18 " +
             "M7 17 L4 20 " +
             "M3 19 L5 21";

var file = "M14 2 H6 A2 2 0 0 0 4 4 V20 A2 2 0 0 0 6 22 H18 A2 2 0 0 0 20 20 V8 L14 2 Z " +
           "M14 2 V8 H20";

// Star-spark (Lucide `sparkles` lightweight).
var sparkle = "M12 3 L13.9 7.1 L18 9 L13.9 10.9 L12 15 L10.1 10.9 L6 9 L10.1 7.1 Z";

var play = "M6 3 L20 12 L6 21 Z";

var alert = "M10.29 3.86 L1.82 18 A2 2 0 0 0 3.53 21 H20.47 A2 2 0 0 0 22.18 18 L13.71 3.86 A2 2 0 0 0 10.29 3.86 Z " +
            "M12 9 V13 " +
            "M12 17 H12.01";

// Counter-clockwise refresh arrow (Lucide `refresh-ccw` simplified).
var refresh = "M3 12 A9 9 0 1 0 6 5.3 L3 8 " +
              "M3 3 V8 H8";

// Standard "open in new" icon — box with an arrow popping out.
var externalLink = "M18 13 V19 A2 2 0 0 1 16 21 H5 A2 2 0 0 1 3 19 V8 A2 2 0 0 1 5 6 H11 " +
                   "M15 3 H21 V9 " +
                   "M10 14 L21 3";

function byName(name) {
    switch (name) {
        case "list":       return list;
        case "zap":        return zap;
        case "settings":   return settings;
        case "plus":       return plus;
        case "x":          return xmark;
        case "check":      return check;
        case "search":     return search;
        case "download":   return download;
        case "trash":      return trash;
        case "folder":     return folder;
        case "folderOpen": return folderOpen;
        case "cpu":        return cpu;
        case "box":        return box;
        case "info":       return info;
        case "chevRight":  return chevRight;
        case "chevDown":   return chevDown;
        case "scissors":   return scissors;
        case "chat":       return chat;
        case "swords":     return swords;
        case "file":       return file;
        case "sparkle":    return sparkle;
        case "play":       return play;
        case "alert":        return alert;
        case "refresh":      return refresh;
        case "externalLink": return externalLink;
        default:             return "";
    }
}
