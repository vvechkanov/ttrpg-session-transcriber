import QtQuick
import QtQuick.Layouts
import App.Theme
import "../controls"

// "Распознавание → Сборка" stepper.
//
// Idle-phase semantics (what this slice renders): both steps are
// `pending` — a number badge plus a dim 2px connector. The live/done/
// failed states arrive in step 5 (AsrWorker wiring); the shape stays
// the same, only colours / badge content flip.
RowLayout {
    id: root

    // "idle" | "asr" | "merge" | "done" | "failed"
    property string phase: "idle"

    spacing: 0

    readonly property var steps: [
        { id: "asr",   label: "Распознавание", sub: "ASR по трекам" },
        { id: "merge", label: "Сборка",        sub: "Мержер таймлайна" }
    ]

    function statusFor(stepId) {
        const order = ["idle", "asr", "merge", "done", "failed"]
        const now = order.indexOf(root.phase)
        const myIdx = ["asr", "merge"].indexOf(stepId) + 1
        if (root.phase === "idle")   return "pending"
        if (root.phase === "done")   return "done"
        if (root.phase === "failed") return stepId === "asr" ? "failed" : "pending"
        if (now === myIdx)           return "active"
        if (now >  myIdx)            return "done"
        return "pending"
    }

    function colorFor(status) {
        switch (status) {
            case "done":   return Theme.green
            case "active": return Theme.accent
            case "failed": return Theme.red
            default:       return Theme.inkFaint
        }
    }

    function bgFor(status) {
        switch (status) {
            case "done":   return Theme.greenSoft
            case "active": return Theme.accentWash
            case "failed": return Theme.redSoft
            default:       return "transparent"
        }
    }

    Repeater {
        model: root.steps

        delegate: RowLayout {
            spacing: 0
            readonly property string stepId: modelData.id
            readonly property string status: root.statusFor(stepId)
            readonly property color  accentColor: root.colorFor(status)
            readonly property int    stepIndex: index

            // Badge + label + sub
            RowLayout {
                Layout.alignment: Qt.AlignVCenter
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    radius: 999
                    color: root.bgFor(status)
                    border.width: 1
                    border.color: accentColor

                    // Pending → number; active → pulsing dot; done →
                    // check; failed → x. Idle phase only paints the
                    // number branch.
                    Text {
                        anchors.centerIn: parent
                        visible: status === "pending"
                        text: (stepIndex + 1).toString()
                        color: accentColor
                        font.family: Theme.fontSans
                        font.pixelSize: 11
                        font.weight: Font.Bold
                    }

                    SvgIcon {
                        anchors.centerIn: parent
                        visible: status === "done"
                        name: "check"; size: 14
                        color: accentColor
                        strokeWidth: 2.4
                    }

                    SvgIcon {
                        anchors.centerIn: parent
                        visible: status === "failed"
                        name: "x"; size: 14
                        color: accentColor
                        strokeWidth: 2.4
                    }

                    Rectangle {
                        anchors.centerIn: parent
                        visible: status === "active"
                        width: 8; height: 8; radius: 8
                        color: accentColor

                        SequentialAnimation on opacity {
                            loops: Animation.Infinite
                            NumberAnimation { from: 1.0; to: 0.4; duration: 700; easing.type: Easing.InOutQuad }
                            NumberAnimation { from: 0.4; to: 1.0; duration: 700; easing.type: Easing.InOutQuad }
                        }
                    }
                }

                ColumnLayout {
                    spacing: 1
                    Text {
                        text: modelData.label
                        color: status === "pending" ? Theme.ink4 : Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: modelData.sub
                        color: Theme.ink4
                        font.family: Theme.fontMono
                        font.pixelSize: 10
                    }
                }
            }

            // Connector line (only between steps).
            Rectangle {
                visible: stepIndex < root.steps.length - 1
                Layout.preferredWidth: 56
                Layout.preferredHeight: 2
                Layout.leftMargin: 14
                Layout.rightMargin: 14
                radius: 2
                color: Theme.border
            }
        }
    }
}
