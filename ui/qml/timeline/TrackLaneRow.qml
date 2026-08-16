import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"
import "../controls/PlayerHues.js" as Hues

// One track (audio lane) row. Left gutter: avatar (initial in hue
// colour) + name / role / character line + per-track model badge. Right
// column: waveform with the Craig segment split drawn across.
//
// Excluded (listener) tracks render at 45% opacity with a muted avatar
// and the italic "слушатель · не ASR" caption.
Item {
    id: root

    property int gutterWidth: 220
    // Default 0 — the host passes real SessionMeta.segmentSplitPct
    // (0 until a folder is opened). The split overlay is hidden at
    // 0 to avoid drawing a dashed line at the start of the waveform.
    property real segmentSplitPct: 0.0

    // Model row index — needed by inline-edit commit handlers so the
    // TrackListModel can be updated by absolute position.
    property int trackIndex: -1

    property string playerName: ""
    property string playerRole: ""
    //: Per-row characters list (raw model data). Used to decide whether
    //: the speaker_map label reads "PC · персонаж…" (placeholder) or
    //: "PC · Aragorn, Legolas". Read-only — edits flow through the
    //: SpeakerMapPopover and the controller, not this row.
    property var characters: []
    //: Pre-joined character display string (`" / "`-separated) used as
    //: a convenience binding when the row only needs to render text.
    //: Falls back to deriving from ``characters`` if the binder didn't
    //: pass the model role through.
    property string characterDisplay: ""
    property bool excluded: false
    property string modelId: ""
    property bool modelOverride: false
    property var peaks: []

    // 0.0 → 1.0. Drives the phase-fill overlay on the waveform.
    property real progress: 0.0

    // Lifecycle state from TrackListModel: idle/queued/running/done/
    // cached/failed. Drives the inline status chip and the fill tint.
    property string trackState: "idle"
    property string errorMessage: ""

    // Per-Craig-segment overlay. Each element is
    // ``{ startPct, endPct, peaks }`` in 0..100 of the track width.
    // Feature #4 iter 4b: every segment gets its own WaveformCanvas
    // positioned inside the row, filled with the peaks the peaks
    // worker computed for that specific audio file.
    property var segments: []

    // Extent of this row's audio on the ruler, 0..100. Falls back to
    // the full lane only when no segments have been published at all —
    // the QML default, which the prototype and the component tests use.
    // Production always publishes at least one segment.
    //
    // Segments of one row can have a gap between them when a Craig
    // recording was restarted; the sweep crosses it linearly. ASR runs
    // serially over the row and reports one number, so there is nothing
    // finer to be faithful to.
    readonly property real _audioStartPct: {
        if (!root.segments || !root.segments.length)
            return 0
        let lo = 100
        for (let i = 0; i < root.segments.length; ++i) {
            const start = root.segments[i].startPct
            lo = Math.min(lo, (start != null && !isNaN(start)) ? start : 0)
        }
        return lo
    }
    readonly property real _audioEndPct: {
        if (!root.segments || !root.segments.length)
            return 100
        let hi = 0
        for (let i = 0; i < root.segments.length; ++i) {
            const end = root.segments[i].endPct
            hi = Math.max(hi, (end != null && !isNaN(end)) ? end : 100)
        }
        return Math.max(hi, root._audioStartPct)
    }

    // True while the pipeline is idle (so fields are safe to edit and
    // the badge can open the override popover).
    property bool editableLocked: false

    signal nameEdited(string newName)
    //: Emitted when the user clicks the read-only speaker_map label
    //: (the line below the player name). The host opens
    //: SpeakerMapPopover.openFor(...) on this signal.
    signal speakerMapClicked()

    // When no per-track override is set, the badge falls back to the
    // globally-active model from ``ModelRegistry``. ``modelRegistry``
    // is a context property in the QML engine, but unit-test harnesses
    // that skip it would leave this binding undefined — use optional
    // chaining and default to "gigaam" so the badge still reads
    // something rather than going blank.
    readonly property string _effectiveModelId: modelId.length > 0
        ? modelId
        : (typeof modelRegistry !== "undefined" && modelRegistry
            ? modelRegistry.activeModelId
            : "gigaam")

    // Phase-aware accent colour for the fill overlay.
    //   cached  → green (bars read as "already on disk")
    //   failed  → muted red (partially-filled bars go red-soft)
    //   whisper → purple override
    //   else    → warm accent
    readonly property color _fillColor: {
        if (trackState === "cached") return Theme.green
        if (trackState === "failed") return Theme.redSoft
        if (modelOverride)           return "#8A6FB8"   // whisper-purple
        return Theme.accent
    }

    signal modelBadgeClicked()

    implicitHeight: 54
    opacity: excluded ? 0.45 : 1.0

    readonly property var hue: Hues.forName(playerName)

    // Row separator
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.borderSoft
    }

    // 3px accent strip at the left when this track is mid-ASR —
    // mirrors the prototype's "runningThis" indicator.
    readonly property bool _running: progress > 0.0 && progress < 1.0
    Rectangle {
        visible: root._running && !root.excluded
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: 6
        anchors.bottomMargin: 7
        width: 3
        color: root._fillColor
        radius: 2
    }

    // ── Left gutter ───────────────────────────────────────────────
    Rectangle {
        id: gutter
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.gutterWidth
        color: "transparent"

        // Right divider
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
            anchors.rightMargin: 10
            spacing: 9

            // Avatar
            Rectangle {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                radius: 999
                color: root.excluded ? Theme.cardAlt : root.hue.base
                border.width: root.excluded ? 1 : 0
                border.color: Theme.border

                Text {
                    anchors.centerIn: parent
                    text: root.playerName.length > 0 ? root.playerName.charAt(0) : ""
                    color: root.excluded ? Theme.ink4 : Theme.accentFg
                    font.family: Theme.fontSans
                    font.pixelSize: 11
                    font.weight: Font.Bold
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                InlineEdit {
                    Layout.fillWidth: true
                    text: root.playerName
                    locked: root.editableLocked || root.excluded
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    font.letterSpacing: -0.05
                    onCommitted: (value) => root.nameEdited(value)
                }

                // Listener row: italic caption, no editable character.
                Text {
                    visible: root.excluded
                    Layout.fillWidth: true
                    text: "слушатель · не ASR"
                    color: Theme.ink3
                    font.family: Theme.fontSans
                    font.pixelSize: 10
                    font.italic: true
                    elide: Text.ElideRight
                }

                // Read-only clickable label. Click opens the
                // SpeakerMapPopover; characters edit there (per
                // feature #5 iter 5b/2). The label collapses
                // multiple character names to a comma-joined string
                // and falls back to a dim "персонаж…" placeholder
                // when the player has no character assigned.
                Item {
                    visible: !root.excluded
                    Layout.fillWidth: true
                    Layout.preferredHeight: speakerLabel.implicitHeight

                    readonly property bool _isGm: root.playerRole === "GM"
                    readonly property string _joined: root.characterDisplay.length > 0
                        ? root.characterDisplay
                        : (root.characters && root.characters.length > 0
                            ? root.characters.join(", ")
                            : "")
                    readonly property bool _hasCharacter: _joined.length > 0

                    Text {
                        id: speakerLabel
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: parent._isGm
                            ? "GM"
                            : (parent._hasCharacter
                                ? "PC · " + parent._joined
                                : "PC · персонаж…")
                        color: parent._isGm || parent._hasCharacter
                            ? Theme.ink3
                            : Theme.inkFaint
                        font.family: Theme.fontSans
                        font.pixelSize: 10
                        font.italic: !parent._isGm && !parent._hasCharacter
                        elide: Text.ElideRight
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.speakerMapClicked()
                    }
                }
            }

            // Model badge (hidden for listeners)
            Rectangle {
                id: modelBadge
                visible: !root.excluded
                Layout.preferredHeight: 18
                implicitWidth: badgeRow.implicitWidth + 12
                radius: Theme.radiusSm
                color: root.modelOverride ? Theme.accentWash : "transparent"
                border.width: 1
                border.color: root.modelOverride ? Theme.accentSoft : Theme.border

                RowLayout {
                    id: badgeRow
                    anchors.centerIn: parent
                    spacing: 3

                    Text {
                        // "Whs" for any whisper-family id (current
                        // canonical "faster-whisper", plus legacy
                        // aliases from saved per-track state), "gAM"
                        // for gigaam and the empty fallback.
                        text: root._effectiveModelId.indexOf("whisper") >= 0
                            ? "Whs" : "gAM"
                        color: root.modelOverride ? Theme.accentDeep : Theme.ink3
                        font.family: Theme.fontMono
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.3
                    }

                    SvgIcon {
                        visible: root.modelOverride
                        name: "alert"; size: 9
                        color: Theme.accentDeep
                        strokeWidth: 2.0
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.modelBadgeClicked()
                }
            }
        }
    }

    // ── Right: waveform + segment split ───────────────────────────
    Item {
        id: track
        anchors.left: gutter.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: 6
        anchors.bottomMargin: 6

        // Feature #4 iter 4b: one WaveformCanvas per Craig segment,
        // positioned at the segment's startPct / endPct on the
        // absolute session timeline. Falls back to a single
        // full-width canvas driven by root.peaks when the model
        // hasn't published segments yet (single-file drop, tests).
        Repeater {
            model: root.segments.length > 0 ? root.segments : [{ startPct: 0, endPct: 100, peaks: root.peaks }]
            delegate: WaveformCanvas {
                readonly property real _startPct: modelData.startPct || 0
                readonly property real _endPct: (modelData.endPct != null) ? modelData.endPct : 100
                x: track.width * (_startPct / 100.0)
                y: 0
                width: Math.max(
                    0,
                    track.width * ((_endPct - _startPct) / 100.0)
                )
                height: track.height
                peaks: modelData.peaks || []
                muted: root.excluded
                // Progress overlay is row-wide, not per-segment — the
                // PipelineController runs ASR serially and exposes a
                // single 0..1 pct per row. Pass 0 here so individual
                // canvases render a static waveform; the row-level
                // progress fill is drawn once below.
                progress: 0.0
                fillColor: root._fillColor
            }
        }

        // Shimmer placeholder for segments whose peaks haven't been
        // decoded yet. Peak extraction is a full ffmpeg decode and
        // takes seconds-to-minutes per track, during which a lane was
        // simply blank — indistinguishable from "nothing here" or
        // "the app hung". Deliberately NOT a fake waveform: it shows
        // that work is in flight without inventing audio that isn't
        // there.
        Repeater {
            model: root.segments.length > 0
                   ? root.segments
                   : [{ startPct: 0, endPct: 100, peaks: root.peaks }]
            delegate: Item {
                readonly property real _startPct: modelData.startPct || 0
                readonly property real _endPct: (modelData.endPct != null) ? modelData.endPct : 100
                readonly property bool _pending: !(modelData.peaks && modelData.peaks.length > 0)

                x: track.width * (_startPct / 100.0)
                y: 0
                width: Math.max(0, track.width * ((_endPct - _startPct) / 100.0))
                height: track.height
                visible: _pending && width > 0
                clip: true

                Rectangle {
                    anchors.fill: parent
                    radius: 3
                    color: root._fillColor
                    opacity: 0.10
                }

                Rectangle {
                    id: sheen
                    width: Math.max(48, parent.width * 0.18)
                    height: parent.height
                    opacity: 0.18
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "transparent" }
                        GradientStop { position: 0.5; color: root._fillColor }
                        GradientStop { position: 1.0; color: "transparent" }
                    }
                    XAnimator on x {
                        running: sheen.parent.visible
                        loops: Animation.Infinite
                        from: -sheen.width
                        to: sheen.parent.width
                        duration: 1400
                    }
                }
            }
        }

        // Progress overlay — one per row, on top of the per-segment
        // canvases, so "N% painted left-to-right" reads as one sweep
        // even though the PipelineController reports a single 0..1 for
        // the whole row.
        //
        // It sweeps the audio, not the lane. The two used to be the
        // same thing: the timeline began at the recording, so a track
        // filled the full width. Now the window spans the whole session
        // and the audio may start well into it — filling from the left
        // edge would put 50% of ASR somewhere in a stretch that has no
        // sound in it at all.
        Rectangle {
            objectName: "progressOverlay"
            visible: root._running && !root.excluded
            x: track.width * (root._audioStartPct / 100.0)
            y: 0
            width: Math.max(
                0,
                track.width
                * ((root._audioEndPct - root._audioStartPct) / 100.0)
                * root.progress
            )
            height: track.height
            color: root._fillColor
            opacity: 0.12
            radius: 2
        }

        // Status chip bottom-anchored. Only renders when the pipeline
        // is active (anything other than the idle state).
        // Pinned to where the audio starts, not to the lane edge. The
        // chip labels this row's ASR run; parking it an hour to the
        // left of the sound it describes made the two look unrelated.
        TrackStatusChip {
            visible: !root.excluded && root.trackState !== "idle"
                     && root.trackState !== "done"
            x: track.width * (root._audioStartPct / 100.0) + 4
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 2
            trackState: root.trackState
            progress: root.progress
            errorMessage: root.errorMessage
        }

        // Vertical dashed segment-split line across the waveform.
        Rectangle {
            visible: root.segmentSplitPct > 0
            x: track.width * (root.segmentSplitPct / 100.0) - 0.5
            y: -6
            width: 1
            height: track.height + 12
            color: "transparent"

            // Render dashes with a pair of semi-transparent children —
            // Rectangle has no dash support. A 1px dashed line is
            // visually subtle enough that four segments read as dashed.
            Repeater {
                model: 18

                delegate: Rectangle {
                    x: 0
                    y: index * ((track.height + 12) / 18)
                    width: 1
                    height: (track.height + 12) / 18 / 2
                    color: Theme.border
                }
            }
        }
    }
}
