import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"
import "ParserBadges.js" as Parsers

// One additional-source lane (chat / combat / notes). Left gutter
// holds the parser icon + title line + file name; the right column
// draws a range bar spanning [startPct..endPct] of the timeline,
// shaded by where events actually occurred.
Item {
    id: root

    property int gutterWidth: 220
    property string parserId: "foundry-chat"
    property string sourceLabel: ""
    property string fileName: ""
    property real startPct: 0.0
    property real endPct: 100.0

    // Real event positions on the ruler, 0..100 — chat messages or
    // combat rolls, straight from the parsed files. Empty means we
    // could not read them, and the bar simply stays plain.
    property var density: []

    // Dimmed state — used later when ASR is running; unused in the
    // idle slice but the prop is available so TimelineScreen can flip
    // it once the phase wires up.
    property bool dim: false

    implicitHeight: 30
    opacity: dim ? 0.5 : 1.0
    Behavior on opacity { NumberAnimation { duration: Theme.animMed } }

    readonly property var parser: Parsers.forId(parserId)
    readonly property string _short: Parsers.shortLabel(parserId)

    // ── Gutter: icon + title + file ───────────────────────────────
    Rectangle {
        id: gutter
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.gutterWidth
        color: "transparent"

        Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 1
            color: Theme.borderSoft
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 6
            spacing: 8

            SvgIcon {
                name: root.parser.icon
                size: 13
                color: root.parser.color
                strokeWidth: 1.7
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: root._short
                        color: Theme.ink2
                        font.family: Theme.fontSans
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        font.letterSpacing: -0.05
                        elide: Text.ElideRight
                    }
                    Text {
                        text: "· " + root.sourceLabel
                        color: Theme.ink4
                        font.family: Theme.fontSans
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                    Item { Layout.fillWidth: true }
                }

                Text {
                    Layout.fillWidth: true
                    text: root.fileName
                    color: Theme.ink4
                    font.family: Theme.fontMono
                    font.pixelSize: 10
                    elide: Text.ElideRight
                }
            }
        }
    }

    // ── Range bar in the right column ─────────────────────────────
    Item {
        id: track
        anchors.left: gutter.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: 5
        anchors.bottomMargin: 5

        Rectangle {
            x: track.width * (root.startPct / 100.0)
            y: 1
            width: track.width * Math.max(0, (root.endPct - root.startPct) / 100.0)
            height: track.height - 2
            radius: 4

            // parser color at low alpha for the fill, stronger for the
            // border. Hex-alpha (#RRGGBBAA) works in Qt.
            color: Qt.rgba(1, 1, 1, 0)
            border.width: 1

            readonly property color _c: root.parser.color

            Component.onCompleted: {
                // Parse the hex color and apply alpha programmatically.
                color = Qt.rgba(_c.r, _c.g, _c.b, 0.07)
                border.color = Qt.rgba(_c.r, _c.g, _c.b, 0.27)
            }

            // Where events actually happened. These used to be 12-18
            // ticks at positions derived from the parser id's character
            // codes — the same comb on every session, labelled in the
            // source as a "content density suggestion". It read as data
            // and was not, so it is gone.
            //
            // Painted rather than instantiated: a busy session carries
            // hundreds of messages, and one item per event is the same
            // trap the waveform fell into.
            Canvas {
                id: densityCanvas
                anchors.fill: parent
                anchors.margins: 2

                readonly property color _tint: root.parser.color

                // Positions are relative to the bar, so a change of
                // either edge invalidates the picture just as much as
                // new data does.
                Connections {
                    target: root
                    function onDensityChanged()  { densityCanvas.requestPaint() }
                    function onStartPctChanged() { densityCanvas.requestPaint() }
                    function onEndPctChanged()   { densityCanvas.requestPaint() }
                }
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()

                onPaint: {
                    const ctx = getContext("2d")
                    ctx.reset()

                    const points = root.density
                    if (!points || points.length === 0 || width <= 0)
                        return

                    // The bar covers [startPct..endPct] of the ruler, so
                    // an event's position has to be re-expressed as a
                    // fraction of the bar, not of the whole timeline.
                    const span = root.endPct - root.startPct
                    if (span <= 0)
                        return

                    // Bucket per pixel column and let overlap darken the
                    // column: that is what makes a flurry of rolls look
                    // different from idle chatter.
                    const columns = Math.max(1, Math.floor(width))
                    const counts = new Array(columns).fill(0)
                    let busiest = 0
                    for (let i = 0; i < points.length; ++i) {
                        const frac = (points[i] - root.startPct) / span
                        if (frac < 0 || frac > 1)
                            continue
                        const col = Math.min(columns - 1, Math.floor(frac * columns))
                        counts[col] += 1
                        if (counts[col] > busiest)
                            busiest = counts[col]
                    }
                    if (busiest === 0)
                        return

                    for (let c = 0; c < columns; ++c) {
                        if (counts[c] === 0)
                            continue
                        // Square root keeps a single message visible
                        // without letting a dense burst wash the rest out.
                        const weight = Math.sqrt(counts[c] / busiest)
                        ctx.fillStyle = Qt.rgba(
                            _tint.r, _tint.g, _tint.b, 0.18 + 0.55 * weight
                        )
                        ctx.fillRect(c, 0, 1, height)
                    }
                }
            }
        }
    }
}
