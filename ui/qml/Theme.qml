pragma Singleton
import QtQuick

QtObject {
    // ── Canvas / surfaces ──────────────────────────────────────────
    readonly property color bg:       "#FAF8F5"
    readonly property color card:     "#FFFFFF"
    readonly property color cardAlt:  "#F5F2EF"
    readonly property color hover:    "#F0ECE6"
    readonly property color scrim:    Qt.rgba(45/255, 37/255, 32/255, 0.32)

    // ── Ink (text) ─────────────────────────────────────────────────
    readonly property color ink:      "#2D2520"
    readonly property color ink2:     "#5A5048"
    readonly property color ink3:     "#6B625A"
    readonly property color ink4:     "#94897E"
    readonly property color inkFaint: "#BBB0A3"

    // ── Borders ────────────────────────────────────────────────────
    readonly property color border:     Qt.rgba(107/255, 98/255, 90/255, 0.18)
    readonly property color borderSoft: Qt.rgba(107/255, 98/255, 90/255, 0.10)

    // ── Accent (burnt ochre) ───────────────────────────────────────
    readonly property color accent:     "#D4843B"
    readonly property color accentDeep: "#B36A26"
    readonly property color accentSoft: "#F7E3C9"
    readonly property color accentWash: "#FCF2E4"
    // Text/icon color on an accent-filled surface.
    // (Named `accentFg`, not `onAccent` — QML parses `on<Capital>` as a
    // signal-handler prefix and rejects the declaration.)
    readonly property color accentFg:   "#FFF9EE"

    // ── Status ─────────────────────────────────────────────────────
    readonly property color green:     "#5A8A3E"
    readonly property color greenSoft: "#E2EDD6"
    readonly property color red:       "#C4472B"
    readonly property color redSoft:   "#F5DACF"
    readonly property color amber:     "#C97A1A"

    // ── Typography ─────────────────────────────────────────────────
    readonly property string fontSans: "Inter, Segoe UI, system-ui, sans-serif"
    readonly property string fontMono: "JetBrains Mono, Fira Code, Menlo, monospace"

    // Prototype scale: 10 / 11 / 11.5 / 12 / 12.5 / 13 / 14 / 16 / 22 px
    readonly property int fontMicro:  10
    readonly property int fontTiny:   11
    readonly property int fontSmall:  12
    readonly property int fontNav:    13   // sidebar nav label (12.5 in prototype; 13 reads crisper on Qt)
    readonly property int fontBody:   13
    readonly property int fontLead:   14
    readonly property int fontH3:     16
    readonly property int fontH1:     22

    // ── Radii ──────────────────────────────────────────────────────
    readonly property int radiusSm:   6
    readonly property int radiusMd:   9
    readonly property int radiusLg:   12
    readonly property int radiusPill: 999

    // ── Spacing (4px base unit) ────────────────────────────────────
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 20
    readonly property int space6: 24
    readonly property int space8: 32

    // ── Layout constants ───────────────────────────────────────────
    readonly property int sidebarWidth: 184

    // ── Animation ──────────────────────────────────────────────────
    readonly property int animFast:   140
    readonly property int animMed:    200
    readonly property int animSlow:   240
}
