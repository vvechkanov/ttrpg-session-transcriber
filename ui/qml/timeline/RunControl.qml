import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import App.Theme
import "../controls"

// Action area next to the phase stepper. Switches presentation based
// on the current phase:
//
//   idle  → primary "Запустить обработку" button
//   asr   → circular progress + percent + ETA + Pause/Cancel pair
//   done  → Refresh + primary "Открыть merged.txt" pair (step 8)
//
// For this slice only `idle` and `asr` are painted — `done` and
// `failed` fall back to the idle button.
Item {
    id: root

    // "idle" | "asr" | "merge" | "done" | "failed"
    property string phase: "idle"

    // Aggregate progress across all running tracks, 0..1. For the
    // step-5 slice this is just the sum of TrackListModel progress
    // values divided by the active-track count.
    property real overallProgress: 0.0

    // Human-readable ETA (computed by the caller). Empty string
    // hides the secondary line — no real estimator yet, so the
    // default is empty rather than a mocked "~1 мин".
    property string etaLabel: ""

    signal runClicked()
    signal pauseClicked()
    signal cancelClicked()
    signal openOutputClicked()

    implicitHeight: 52

    //: Publish the width of whichever state-specific child is currently
    //: visible so the surrounding RowLayout in TimelineScreen allocates
    //: enough horizontal space — without this the Item is sized 0 and
    //: its anchored children render on top of EngineBar to its left.
    implicitWidth: {
        if (root.phase === "done") return doneRow.implicitWidth
        if (root.phase === "asr" || root.phase === "merge") return runningCard.implicitWidth
        return idleButton.implicitWidth
    }

    // Idle / failed → single primary "Запустить" button.
    PrimaryButton {
        id: idleButton
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        visible: root.phase === "idle" || root.phase === "failed"
        sizeTag: "md"
        iconName: "play"
        text: "Запустить обработку"
        onClicked: root.runClicked()
    }

    // Done → Refresh (ghost) + "Открыть merged.txt" (primary).
    // The refresh button re-runs the whole pipeline; the primary one
    // opens the produced .txt via OS default handler (wired at
    // TimelineScreen level through `openOutputClicked`).
    RowLayout {
        id: doneRow
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        visible: root.phase === "done"
        spacing: 8

        GhostButton {
            sizeTag: "md"
            iconName: "refresh"
            text: "Перезапустить"
            onClicked: root.runClicked()
        }

        PrimaryButton {
            sizeTag: "md"
            iconName: "externalLink"
            text: "Открыть merged.txt"
            onClicked: root.openOutputClicked()
        }
    }

    Rectangle {
        id: runningCard
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        visible: root.phase === "asr" || root.phase === "merge"
        implicitHeight: 52
        implicitWidth: runningRow.implicitWidth + 30
        radius: 10
        color: Theme.accentWash
        border.width: 1
        border.color: Theme.accentSoft

        RowLayout {
            id: runningRow
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 16
            spacing: 14

            // Circular progress dial
            Item {
                id: dial
                Layout.preferredWidth: 30
                Layout.preferredHeight: 30

                readonly property real r:  12
                readonly property real cx: 15
                readonly property real cy: 15

                Shape {
                    anchors.fill: parent
                    layer.enabled: true
                    layer.samples: 4

                    ShapePath {
                        strokeColor: Theme.accentSoft
                        strokeWidth: 2.8
                        fillColor: "transparent"
                        capStyle: ShapePath.RoundCap
                        PathAngleArc {
                            centerX: dial.cx
                            centerY: dial.cy
                            radiusX: dial.r
                            radiusY: dial.r
                            startAngle: -90
                            sweepAngle: 360
                        }
                    }

                    ShapePath {
                        strokeColor: Theme.accent
                        strokeWidth: 2.8
                        fillColor: "transparent"
                        capStyle: ShapePath.RoundCap
                        PathAngleArc {
                            centerX: dial.cx
                            centerY: dial.cy
                            radiusX: dial.r
                            radiusY: dial.r
                            startAngle: -90
                            sweepAngle: root.overallProgress * 360
                        }
                    }
                }
            }

            // Percent + ETA. Merge phase shows "Сборка…" instead of a
            // second-line ETA since gap stitching is quick enough that
            // an ETA feels misleading.
            ColumnLayout {
                spacing: 1

                Text {
                    text: Math.round(root.overallProgress * 100) + "%"
                    color: Theme.accentDeep
                    font.family: Theme.fontMono
                    font.pixelSize: 15
                    font.weight: Font.Bold
                    font.letterSpacing: -0.3
                }

                Text {
                    visible: text.length > 0
                    text: root.phase === "merge"
                        ? "Сборка…"
                        : (root.etaLabel.length > 0
                            ? root.etaLabel + " осталось"
                            : "")
                    color: Theme.accentDeep
                    opacity: 0.8
                    font.family: Theme.fontSans
                    font.pixelSize: 11
                }
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 28
                color: Theme.accentSoft
            }

            GhostButton {
                sizeTag: "sm"
                plain: true
                iconName: "x"
                text: "Отмена"
                onClicked: root.cancelClicked()
            }
        }
    }
}
