import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App.Theme
import "../controls"
import "../controls/PlayerHues.js" as Hues

// Per-track speaker_map.json editor.
//
// Mirrors the structure of TrackOverridePopover: header (avatar +
// title + close), body (player name field, role toggle, dynamic
// characters list), footer (cancel + save). Save emits
// `saved(row, player, role, characters)` and the parent screen wires
// it into PipelineController.saveSpeakerMapEntry.
//
// Opening:
//     popover.openFor(row, trackName, player, role, characters)
//
// `role` is the speaker_map enum string ("GM" | "PC") — the popover
// does not need to know about TrackEntry's own role enum.
Popup {
    id: root
    // Stable name so test harnesses (and future a11y consumers) can
    // reach the popover via QObject.findChild without depending on
    // QML id resolution across file boundaries.
    objectName: "speakerMapPopover"

    property int targetRow: -1
    property string trackName: ""

    // Initial values populated when openFor() is called. The popover
    // copies them into mutable working state below so the user can
    // cancel without leaking edits back into the model.
    property string initialPlayer: ""
    property string initialRole: "PC"
    property var initialCharacters: []

    // Mutable working state edited by the controls below. Always reset
    // by openFor() so a cancel-then-reopen cycle starts clean.
    property string _player: ""
    property string _role: "PC"
    //: Plain JS array of strings — new empty entries get appended by
    //: the "+ Добавить" button and Repeater below redraws.
    property var _characters: []

    width: 380
    padding: 0

    modal: true
    dim: false
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

    signal saved(int row, string player, string role, var characters)

    function openFor(row, name, player, role, characters) {
        targetRow = row
        trackName = name
        initialPlayer = player || ""
        initialRole = (role === "GM") ? "GM" : "PC"
        initialCharacters = characters || []

        _player = initialPlayer
        _role = initialRole
        // Take a defensive copy — assigning the inbound array directly
        // would alias the caller's list and edits below would mutate
        // the model row's characters in place. `slice()` makes a new
        // array of the same string elements (strings are immutable so
        // a shallow copy is enough).
        _characters = (initialCharacters || []).slice()
        open()
    }

    function _addCharacter() {
        const next = _characters.slice()
        next.push("")
        _characters = next
    }

    function _removeCharacter(idx) {
        if (idx < 0 || idx >= _characters.length) return
        const next = _characters.slice()
        next.splice(idx, 1)
        _characters = next
    }

    function _setCharacter(idx, value) {
        if (idx < 0 || idx >= _characters.length) return
        if (_characters[idx] === value) return
        const next = _characters.slice()
        next[idx] = value
        _characters = next
    }

    function _commit() {
        // Filter empty / whitespace-only strings before emitting. The
        // core normaliser strips them anyway, but keeping the signal
        // payload clean makes downstream debugging easier.
        const cleaned = []
        for (let i = 0; i < _characters.length; ++i) {
            const v = (_characters[i] || "").trim()
            if (v.length > 0) cleaned.push(v)
        }
        if (root.targetRow >= 0) {
            root.saved(root.targetRow, _player, _role, cleaned)
        }
        root.close()
    }

    readonly property var _hue: Hues.forName(trackName)

    background: Rectangle {
        radius: Theme.radiusLg
        color: Theme.card
        border.width: 1
        border.color: Theme.border

        Rectangle {
            z: -1
            anchors.fill: parent
            anchors.margins: -6
            radius: parent.radius + 2
            color: Qt.rgba(45/255, 37/255, 32/255, 0.12)
            opacity: 0.35
        }
    }

    contentItem: ColumnLayout {
        spacing: 0

        // ── Header ──────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 14
            spacing: 10

            Rectangle {
                Layout.preferredWidth: 26
                Layout.preferredHeight: 26
                radius: 999
                color: root._hue.base

                Text {
                    anchors.centerIn: parent
                    text: root.trackName.length > 0 ? root.trackName.charAt(0) : ""
                    color: Theme.accentFg
                    font.family: Theme.fontSans
                    font.pixelSize: 11
                    font.weight: Font.Bold
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    Layout.fillWidth: true
                    text: "Speaker map · " + root.trackName
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    text: "Имя игрока, роль и список персонажей этой дорожки"
                    color: Theme.ink4
                    font.family: Theme.fontSans
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }
            }

            Rectangle {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                radius: 4
                color: closeMa.containsMouse ? Theme.cardAlt : "transparent"

                SvgIcon {
                    anchors.centerIn: parent
                    name: "x"; size: 14
                    color: Theme.ink4
                    strokeWidth: 1.8
                }
                MouseArea {
                    id: closeMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.close()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.borderSoft
        }

        // ── Body ────────────────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: 14
            spacing: 12

            // Player name --------------------------------------
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 5

                Text {
                    text: "ИГРОК"
                    color: Theme.ink3
                    font.family: Theme.fontSans
                    font.pixelSize: 10
                    font.weight: Font.Bold
                    font.letterSpacing: 0.7
                }

                TextInputField {
                    Layout.fillWidth: true
                    text: root._player
                    // Surface the audio stem as a hint when the field
                    // is empty — fresh rows open the popover with no
                    // pre-filled player and the stem ("1-alice") is
                    // the closest signal the user has to which row
                    // they're editing.
                    placeholderText: root.trackName.length > 0
                        ? root.trackName
                        : "Имя игрока"
                    onTextChanged: root._player = text
                }
            }

            // Role toggle (GM / PC) ----------------------------
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 5

                Text {
                    text: "РОЛЬ"
                    color: Theme.ink3
                    font.family: Theme.fontSans
                    font.pixelSize: 10
                    font.weight: Font.Bold
                    font.letterSpacing: 0.7
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Repeater {
                        model: ["PC", "GM"]

                        delegate: Rectangle {
                            readonly property bool isActive: modelData === root._role
                            implicitHeight: 28
                            implicitWidth: roleTxt.implicitWidth + 22
                            radius: 5
                            color: isActive ? Theme.accentWash : Theme.card
                            border.width: 1
                            border.color: isActive ? Theme.accentSoft : Theme.border

                            Text {
                                id: roleTxt
                                anchors.centerIn: parent
                                text: modelData
                                color: parent.isActive ? Theme.accentDeep : Theme.ink2
                                font.family: Theme.fontSans
                                font.pixelSize: 12
                                font.weight: parent.isActive ? Font.DemiBold : Font.Medium
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root._role = modelData
                            }
                        }
                    }
                }
            }

            // Characters list (only meaningful for PC) ---------
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                visible: root._role !== "GM"

                Text {
                    text: "ПЕРСОНАЖИ"
                    color: Theme.ink3
                    font.family: Theme.fontSans
                    font.pixelSize: 10
                    font.weight: Font.Bold
                    font.letterSpacing: 0.7
                }

                Repeater {
                    model: root._characters

                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        TextInputField {
                            Layout.fillWidth: true
                            text: modelData
                            placeholderText: "Имя персонажа"
                            onTextChanged: root._setCharacter(index, text)
                        }

                        Rectangle {
                            Layout.preferredWidth: 28
                            Layout.preferredHeight: 28
                            radius: 4
                            color: removeMa.containsMouse ? Theme.cardAlt : "transparent"
                            border.width: 1
                            border.color: Theme.border

                            SvgIcon {
                                anchors.centerIn: parent
                                name: "x"; size: 12
                                color: Theme.ink3
                                strokeWidth: 1.8
                            }

                            MouseArea {
                                id: removeMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root._removeCharacter(index)
                            }
                        }
                    }
                }

                GhostButton {
                    Layout.fillWidth: true
                    sizeTag: "sm"
                    text: "+ Добавить персонажа"
                    onClicked: root._addCharacter()
                }
            }

            // GM hint (replaces the characters list when GM is active)
            Text {
                visible: root._role === "GM"
                Layout.fillWidth: true
                text: "ГМ — без персонажа. Реплики пишутся как «Мастер»."
                color: Theme.ink3
                font.family: Theme.fontSans
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }

        // ── Footer ──────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            color: Theme.cardAlt
            implicitHeight: footerRow.implicitHeight + 20

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 1
                color: Theme.borderSoft
            }

            RowLayout {
                id: footerRow
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                anchors.topMargin: 10
                anchors.bottomMargin: 10
                spacing: 8

                GhostButton {
                    sizeTag: "sm"
                    plain: true
                    text: "Отмена"
                    onClicked: root.close()
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    sizeTag: "sm"
                    text: "Сохранить"
                    onClicked: root._commit()
                }
            }
        }
    }
}
