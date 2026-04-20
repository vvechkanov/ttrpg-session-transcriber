import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App.Theme
import "../controls"
import "../popovers"
import "../timeline"

// Timeline / session working view.
//
// This slice renders the full idle-phase layout:
//   SessionTopBar
//   └ scrollable body
//      ├ Stepper + engine + run control card
//      ├ TimelineCanvas
//      │    Ruler header (sources panel caption)
//      │    SourceLaneRow × N
//      │    "+ добавить источник"
//      │    Ruler header (tracks panel caption "5 из 6")
//      │    TrackLaneRow × N
//      │    "+ добавить аудиодорожку"
//      │    CraigSegmentsStrip
//      └ MergerChip ─── divider ─── OutputChip
//
// Non-idle states (asr / merge / done / failed) are wired by later
// slices. This widget ignores `phase` beyond showing the idle Run
// button.
Rectangle {
    id: root
    color: Theme.bg

    // Single source of truth for phase is appModel.phase — wired via a
    // context property from Python. The local binding keeps template
    // code terse (`root.phase`) and reacts to external mutations.
    readonly property string phase: appModel ? appModel.phase : "idle"
    property int _gutterWidth: 220

    // ── Popovers / overlays ──────────────────────────────────────
    TrackOverridePopover {
        id: overridePopover
        parent: root
        x: 22
        onChosen: (row, optionId) => {
            if (tracksModel) {
                tracksModel.setModelOverride(row, optionId)
            }
        }
    }

    // Vertical layout: sticky bar on top, scrollable body below.
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SessionTopBar {
            Layout.fillWidth: true
            z: 2
            campaignTitle:   sessionMeta ? sessionMeta.campaignTitle   : ""
            sessionTitle:    sessionMeta ? sessionMeta.sessionTitle    : ""
            segmentsCaption: sessionMeta ? sessionMeta.segmentsCaption : ""
            activeTab: "process"
        }

        Flickable {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: width
            contentHeight: body.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            Item {
                id: body
                width: parent.width
                implicitHeight: layout.implicitHeight + 52

                ColumnLayout {
                    id: layout
                    anchors.top: parent.top
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(parent.width - 48, 1320)
                    anchors.topMargin: 20
                    spacing: 16

                    // ── Stepper + engine + run control ────────────
                    Rectangle {
                        Layout.fillWidth: true
                        radius: Theme.radiusLg
                        color: Theme.card
                        border.width: 1
                        border.color: Theme.border
                        implicitHeight: stepperRow.implicitHeight + 32

                        RowLayout {
                            id: stepperRow
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 16

                            PhaseStepper { phase: root.phase }

                            Item { Layout.fillWidth: true }

                            EngineBar {}

                            RunControl {
                                phase: root.phase
                                overallProgress: root.phase === "merge"
                                    ? (appModel ? appModel.mergeProgress : 0.0)
                                    : (tracksModel ? tracksModel.overallProgress : 0.0)
                                etaLabel: "~1 мин"
                                onRunClicked: pipeline.runAsr()
                                onCancelClicked: pipeline.cancel()
                                onOpenOutputClicked: {
                                    if (pipeline && pipeline.outputPath.length > 0) {
                                        Qt.openUrlExternally("file://" + pipeline.outputPath)
                                    }
                                }
                            }
                        }
                    }

                    // ── Done summary banner ───────────────────────
                    DoneSummary {
                        visible: root.phase === "done"
                        durationLabel: (appModel && appModel.doneSummary.durationLabel)
                            ? appModel.doneSummary.durationLabel
                            : ""
                        statsLine: (appModel && appModel.doneSummary.statsLine)
                            ? appModel.doneSummary.statsLine
                            : ""
                    }

                    // ── Timeline card ─────────────────────────────
                    Rectangle {
                        id: timelineCard
                        Layout.fillWidth: true
                        radius: Theme.radiusLg
                        color: Theme.card
                        border.width: 1
                        border.color: Theme.border
                        clip: true
                        implicitHeight: timelineCol.implicitHeight

                        ColumnLayout {
                            id: timelineCol
                            anchors.fill: parent
                            spacing: 0

                            // ── Sources header (caption + ruler) ──
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 30
                                color: Theme.cardAlt

                                RowLayout {
                                    anchors.fill: parent
                                    spacing: 0

                                    Rectangle {
                                        Layout.preferredWidth: root._gutterWidth
                                        Layout.fillHeight: true
                                        color: "transparent"

                                        Rectangle {
                                            anchors.right: parent.right
                                            anchors.top: parent.top
                                            anchors.bottom: parent.bottom
                                            width: 1
                                            color: Theme.borderSoft
                                        }

                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            x: 12
                                            text: "ДОПОЛНИТЕЛЬНЫЕ ИСТОЧНИКИ"
                                            color: Theme.ink3
                                            font.family: Theme.fontSans
                                            font.pixelSize: 10
                                            font.weight: Font.Bold
                                            font.letterSpacing: 1.0
                                        }
                                    }

                                    // Ruler in the sources header is purely cosmetic —
                                    // the "real" ruler for reading time sits on the
                                    // tracks header below.
                                    TimelineRuler {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        totalMinutes: sessionMeta ? sessionMeta.totalMinutes : 227
                                        segmentSplitPct: sessionMeta ? sessionMeta.segmentSplitPct : 66.0
                                    }
                                }
                            }

                            // ── Source lanes ──────────────────────
                            // Rectangle + ColumnLayout: the layout is
                            // top-anchored (not anchors.fill) so the
                            // Rectangle can derive its height from the
                            // layout's implicitHeight. anchors.fill +
                            // implicitHeight: childrenRect.height would
                            // collapse to zero because anchored children
                            // don't contribute to childrenRect.
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: sourcesCol.implicitHeight
                                color: Theme.bg

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    height: 1
                                    color: Theme.borderSoft
                                    z: 1
                                }

                                ColumnLayout {
                                    id: sourcesCol
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    spacing: 0

                                    Repeater {
                                        model: sourcesModel

                                        delegate: SourceLaneRow {
                                            Layout.fillWidth: true
                                            gutterWidth: root._gutterWidth
                                            parserId:    model.parserId
                                            sourceLabel: model.label
                                            fileName:    model.fileName
                                            startPct:    model.startPct
                                            endPct:      model.endPct
                                        }
                                    }

                                    AddInlineRow {
                                        Layout.fillWidth: true
                                        gutterWidth: root._gutterWidth
                                        label: "добавить источник"
                                    }
                                }
                            }

                            // ── Tracks header ─────────────────────
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 30
                                color: Theme.cardAlt

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    height: 1
                                    color: Theme.borderSoft
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    spacing: 0

                                    Rectangle {
                                        Layout.preferredWidth: root._gutterWidth
                                        Layout.fillHeight: true
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
                                            anchors.rightMargin: 12
                                            spacing: 4

                                            Text {
                                                text: "АУДИОДОРОЖКИ"
                                                color: Theme.ink3
                                                font.family: Theme.fontSans
                                                font.pixelSize: 10
                                                font.weight: Font.Bold
                                                font.letterSpacing: 1.0
                                            }

                                            Text {
                                                text: "· " + (tracksModel ? tracksModel.activeCount() : 0) + " из " + (tracksModel ? tracksModel.rowCount() : 0)
                                                color: Theme.ink4
                                                font.family: Theme.fontMono
                                                font.pixelSize: 10
                                                font.weight: Font.Medium
                                            }

                                            Item { Layout.fillWidth: true }
                                        }
                                    }

                                    TimelineRuler {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        totalMinutes: sessionMeta ? sessionMeta.totalMinutes : 227
                                        segmentSplitPct: sessionMeta ? sessionMeta.segmentSplitPct : 66.0
                                    }
                                }
                            }

                            // ── Track rows (with stitch overlay) ──
                            // Wrapped in an Item so StitchOverlay can
                            // sit absolutely on top of just the track
                            // lanes — not the whole timeline card.
                            Item {
                                Layout.fillWidth: true
                                implicitHeight: tracksCol.implicitHeight

                                ColumnLayout {
                                    id: tracksCol
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    spacing: 0

                                    Repeater {
                                        model: tracksModel

                                        delegate: TrackLaneRow {
                                            id: trackDelegate
                                            Layout.fillWidth: true
                                            trackIndex:    index
                                            gutterWidth:   root._gutterWidth
                                            segmentSplitPct: sessionMeta ? sessionMeta.segmentSplitPct : 66.0
                                            playerName:    model.name
                                            playerRole:    model.playerRole
                                            character:     model.character
                                            excluded:      model.excluded
                                            modelId:       model.modelId
                                            modelOverride: model.override
                                            peaks:         model.peaks
                                            progress:      model.progress
                                            trackState:    model.trackState
                                            errorMessage:  model.errorMessage
                                            editableLocked: root.phase !== "idle"
                                            onNameEdited: (value) => {
                                                if (tracksModel) tracksModel.setPlayerName(index, value)
                                            }
                                            onCharacterEdited: (value) => {
                                                if (tracksModel) tracksModel.setCharacter(index, value)
                                            }
                                            onModelBadgeClicked: {
                                                if (root.phase !== "idle") return
                                                const rowY = trackDelegate.mapToItem(root, 0, trackDelegate.height).y
                                                overridePopover.y = Math.max(64, rowY)
                                                overridePopover.openFor(
                                                    index, model.name, model.modelId, model.override
                                                )
                                            }
                                        }
                                    }

                                    AddInlineRow {
                                        Layout.fillWidth: true
                                        gutterWidth: root._gutterWidth
                                        label: "добавить аудиодорожку"
                                    }
                                }

                                StitchOverlay {
                                    anchors.fill: tracksCol
                                    visible: root.phase === "merge"
                                    gutterWidth: root._gutterWidth
                                    stitches: appModel ? appModel.mergeStitches : []
                                }
                            }

                            CraigSegmentsStrip {
                                Layout.fillWidth: true
                                gutterWidth: root._gutterWidth
                                segmentSplitPct: sessionMeta ? sessionMeta.segmentSplitPct : 66.0
                            }
                        }
                    }

                    // ── Merger chip + divider + output chip ───────
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12

                        MergerChip {
                            active: root.phase === "merge"
                            gapCount: appModel ? appModel.mergeStitches.length : 0
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.borderSoft
                        }

                        OutputChip {
                            done: root.phase === "done"
                            outputPath: pipeline ? pipeline.outputPath : ""
                            sizeCaption: (appModel && appModel.doneSummary.fileSize)
                                ? appModel.doneSummary.fileSize
                                : "—"
                        }
                    }

                    // ── Transcript preview (done phase only) ──────
                    TranscriptPreview {
                        visible: root.phase === "done"
                        filePath:      pipeline ? pipeline.outputPath : ""
                        fileSize:      (appModel && appModel.doneSummary.fileSize)      ? appModel.doneSummary.fileSize      : ""
                        wordCount:     (appModel && appModel.doneSummary.wordCount)     ? appModel.doneSummary.wordCount     : ""
                        cueCount:      (appModel && appModel.doneSummary.cueCount)      ? appModel.doneSummary.cueCount      : ""
                        sessionLength: (appModel && appModel.doneSummary.sessionLength) ? appModel.doneSummary.sessionLength : ""
                        onOpenClicked: {
                            if (pipeline && pipeline.outputPath.length > 0) {
                                Qt.openUrlExternally("file://" + pipeline.outputPath)
                            }
                        }
                        onRevealInFolderClicked: {
                            if (pipeline && pipeline.outputPath.length > 0) {
                                // Strip the filename so the handler opens the
                                // containing folder (Finder / Explorer).
                                const parts = pipeline.outputPath.split("/")
                                parts.pop()
                                Qt.openUrlExternally("file://" + parts.join("/"))
                            }
                        }
                    }
                }
            }
        }
    }
}
