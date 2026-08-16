import QtQuick
import App.Theme

// Waveform with a phase-driven fill overlay.
//
// Peaks come from core.peaks.get_or_compute_peaks via PeaksWorker on
// a background QThread — an ffmpeg-decoded max(abs(x)) reduction
// cached as <audio>.peaks.bin. An empty peaks list renders an empty
// lane (used before extraction finishes on ingest).
//
// Bars are downsampled to whatever fits the lane. core.peaks emits
// DEFAULT_BIN_COUNT = 2000 values, and a lane is ~1100-1500 px wide:
// one item per value cannot fit and never could. The previous version
// laid the values out with a Repeater and a fixed 1.5 px gap, so the
// gaps alone demanded ~3000 px and the computed bar width came out
// *negative* — Qt draws nothing for a negative width, which is why no
// real session ever showed a waveform. The prototype's ~100 fake peaks
// happened to fit, so the arithmetic looked fine.
//
// Painting instead of instantiating is also the right shape: 2000
// Rectangles per lane across six lanes is 12 000 scene-graph nodes for
// what is one static picture per track.
Canvas {
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
    readonly property real _gap: 1
    readonly property real _minBarWidth: 1.5

    // How many bars actually fit, never more than we have data for:
    // stretching 200 values across 400 bars would invent detail that
    // was never decoded.
    readonly property int _barCount: {
        const n = peaks ? peaks.length : 0
        if (n === 0 || width <= 2 * _padX)
            return 0
        const fits = Math.floor(
            (width - 2 * _padX + _gap) / (_minBarWidth + _gap)
        )
        return Math.max(1, Math.min(n, fits))
    }

    onPeaksChanged: requestPaint()
    onProgressChanged: requestPaint()
    onMutedChanged: requestPaint()
    onFillColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()

        const bars = _barCount
        if (bars === 0)
            return

        const values = peaks
        const total = values.length
        const pitch = (width - 2 * _padX) / bars
        const barW = Math.max(_minBarWidth, pitch - _gap)
        const filledUntil = Math.round(progress * bars)

        for (let i = 0; i < bars; ++i) {
            // Bucket maximum, not average: peaks exist to show where
            // sound happened, and averaging flattens a short loud
            // syllable into the surrounding silence.
            const from = Math.floor(i * total / bars)
            const to = Math.max(from + 1, Math.floor((i + 1) * total / bars))
            let peak = 0
            for (let k = from; k < to && k < total; ++k) {
                const v = values[k]
                if (v > peak)
                    peak = v
            }

            const h = Math.max(_minHeight, (peak * 0.8 + 0.15) * height)
            ctx.fillStyle = i < filledUntil ? fillColor : baseColor
            ctx.fillRect(
                _padX + i * pitch,
                (height - h) / 2,
                barW,
                h
            )
        }
    }
}
