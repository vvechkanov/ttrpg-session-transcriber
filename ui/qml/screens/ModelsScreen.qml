import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App.Theme
import "../controls"
import "../drawers"

// Models manager screen.
//
// Layout:
//   ┌ title row: "Модели распознавания" │ + Добавить модель ──┐
//   │ helper copy                                             │
//   │ ┌ search input ─── Все  │ Установленные │ Доступные ─┐ │
//   │ ┌ card ──────────────────────────────────────────────┐ │
//   │ │ header row (columns)                               │ │
//   │ │ ModelRow × N                                       │ │
//   │ └────────────────────────────────────────────────────┘ │
//   │ ┌ disk-usage strip ──────────────────────────────────┐ │
//   └─────────────────────────────────────────────────────────┘
//
// Centered in a max-width 1200 column on a Theme.bg background, with
// horizontal scrolling disabled and vertical scrolling handled by the
// outer Flickable.
Rectangle {
    id: root
    color: Theme.bg

    ModelDetailsDrawer { id: drawer }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: page.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Item {
            id: page
            width: parent.width
            implicitHeight: column.implicitHeight + 80

            ColumnLayout {
                id: column
                anchors.top: parent.top
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(parent.width - 64, 1200)
                anchors.topMargin: 32
                spacing: 0

                // ── Title row ─────────────────────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 16

                    Text {
                        text: "Модели распознавания"
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: Theme.fontH1
                        font.weight: Font.Bold
                        font.letterSpacing: -0.4
                    }

                    Item { Layout.fillWidth: true }

                    PrimaryButton {
                        sizeTag: "md"
                        iconName: "plus"
                        text: "Добавить модель"
                    }
                }

                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    Layout.maximumWidth: 680
                    text: "Установленные модели хранятся локально и работают без интернета. Активная используется по умолчанию для новых сессий — на конкретной дорожке можно переопределить."
                    color: Theme.ink3
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                }

                // ── Search + filter toolbar ───────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 24
                    spacing: 10

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        radius: Theme.radiusSm + 2
                        color: Theme.card
                        border.width: 1
                        border.color: Theme.border

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 8

                            SvgIcon {
                                name: "search"; size: 14
                                color: Theme.ink4
                                strokeWidth: 1.6
                            }

                            Text {
                                Layout.fillWidth: true
                                text: "Поиск по названию, языку, размеру…"
                                color: Theme.ink4
                                font.family: Theme.fontSans
                                font.pixelSize: 13
                            }
                        }
                    }

                    // Three filter buttons — static visuals for this
                    // slice. Wiring to a filter proxy happens later.
                    GhostButton { sizeTag: "md"; text: "Все" }
                    GhostButton { sizeTag: "md"; plain: true; text: "Установленные" }
                    GhostButton { sizeTag: "md"; plain: true; text: "Доступные" }
                }

                // ── Models table ──────────────────────────────────
                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 18
                    radius: Theme.radiusLg
                    color: Theme.card
                    border.width: 1
                    border.color: Theme.border
                    clip: true
                    implicitHeight: tableCol.implicitHeight

                    ColumnLayout {
                        id: tableCol
                        anchors.fill: parent
                        spacing: 0

                        // Header row
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            color: Theme.cardAlt

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 16
                                anchors.rightMargin: 16
                                spacing: 16

                                Text {
                                    Layout.fillWidth: true
                                    Layout.horizontalStretchFactor: 26
                                    Layout.minimumWidth: 260
                                    text: "МОДЕЛЬ"
                                    color: Theme.ink3
                                    font.family: Theme.fontSans
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    font.letterSpacing: 1.0
                                }
                                Text {
                                    Layout.preferredWidth: 90
                                    text: "РАЗМЕР"
                                    color: Theme.ink3
                                    font.family: Theme.fontSans
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    font.letterSpacing: 1.0
                                }
                                Text {
                                    Layout.preferredWidth: 80
                                    text: "ЯЗЫК"
                                    color: Theme.ink3
                                    font.family: Theme.fontSans
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    font.letterSpacing: 1.0
                                }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.horizontalStretchFactor: 10
                                    Layout.minimumWidth: 100
                                    text: "ТОЧНОСТЬ"
                                    color: Theme.ink3
                                    font.family: Theme.fontSans
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    font.letterSpacing: 1.0
                                }
                                Text {
                                    Layout.preferredWidth: 110
                                    text: "СКОРОСТЬ"
                                    color: Theme.ink3
                                    font.family: Theme.fontSans
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    font.letterSpacing: 1.0
                                }
                                Text {
                                    Layout.preferredWidth: 170
                                    horizontalAlignment: Text.AlignRight
                                    text: "ДЕЙСТВИЕ"
                                    color: Theme.ink3
                                    font.family: Theme.fontSans
                                    font.pixelSize: 10
                                    font.weight: Font.Bold
                                    font.letterSpacing: 1.0
                                }
                            }

                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                height: 1
                                color: Theme.borderSoft
                            }
                        }

                        // Per-row busy state — keyed by the row index.
                        // Set from ModelRegistry.installProgress /
                        // installFinished / installFailed below; read
                        // by ModelRow delegates via `busyRow` bindings.
                        QtObject {
                            id: busy
                            property int row: -1
                            property string kind: ""   // "install" | "uninstall"
                            property int pct: 0
                            property string note: ""

                            function beginInstall(r)   { row = r; kind = "install";   pct = 0; note = "" }
                            function beginUninstall(r) { row = r; kind = "uninstall"; pct = 0; note = "" }
                            function clear()           { row = -1; kind = "";         pct = 0; note = "" }
                        }

                        Connections {
                            target: modelRegistry
                            function onInstallProgress(row, pct, note) {
                                busy.row = row
                                busy.kind = busy.kind === "uninstall" ? "uninstall" : "install"
                                busy.pct = pct
                                busy.note = note
                            }
                            function onInstallFinished(row) { busy.clear() }
                            function onInstallFailed(row, message) { busy.clear() }
                        }

                        // Rows
                        Repeater {
                            model: modelRegistry

                            ModelRow {
                                Layout.fillWidth: true
                                modelName: model.name
                                vendor: model.vendor
                                size: model.size
                                lang: model.lang
                                accuracy: model.accuracy
                                speed: model.speed
                                installed: model.installed
                                active: model.active
                                lastRow: index === modelRegistry.rowCount() - 1
                                busyKind: busy.row === index ? busy.kind : ""
                                busyPct:  busy.row === index ? busy.pct  : 0
                                busyNote: busy.row === index ? busy.note : ""
                                onRowClicked: drawer.openFor(modelRegistry.entryAt(index))
                                onActivateClicked: modelRegistry.setActive(index)
                                onInstallClicked: {
                                    busy.beginInstall(index)
                                    modelRegistry.install(index)
                                }
                                onUninstallClicked: {
                                    busy.beginUninstall(index)
                                    modelRegistry.uninstall(index)
                                }
                            }
                        }
                    }
                }

                // ── Disk-usage strip ──────────────────────────────
                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 20
                    radius: Theme.radiusLg - 2
                    color: Theme.card
                    border.width: 1
                    border.color: Theme.borderSoft
                    implicitHeight: storageRow.implicitHeight + 28

                    RowLayout {
                        id: storageRow
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        anchors.topMargin: 14
                        anchors.bottomMargin: 14
                        spacing: 14

                        SvgIcon {
                            name: "box"; size: 18
                            color: Theme.ink3
                            strokeWidth: 1.7
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                Text {
                                    text: "Занято на диске: "
                                    color: Theme.ink2
                                    font.family: Theme.fontSans
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: modelRegistry.installedSizeLabel
                                    color: Theme.ink2
                                    font.family: Theme.fontMono
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: " · " + modelRegistry.installedCount
                                          + " из " + modelRegistry.rowCount() + " моделей"
                                    color: Theme.ink2
                                    font.family: Theme.fontSans
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                }
                                Item { Layout.fillWidth: true }
                            }

                            // Per-backend stacked bar removed — the
                            // 9/18/70 split was hardcoded mock
                            // proportions. A real stacked view needs
                            // per-backend size, which is already shown
                            // in each row's size column.
                        }

                        GhostButton {
                            sizeTag: "sm"
                            text: "Открыть папку моделей"
                            enabled: modelRegistry.modelsRoot().length > 0
                            onClicked: {
                                var p = modelRegistry.modelsRoot()
                                if (p.length === 0) return
                                var u = p.replace(/\\/g, "/")
                                Qt.openUrlExternally(u.charAt(0) === "/"
                                    ? ("file://" + u)
                                    : ("file:///" + u))
                            }
                        }
                    }
                }
            }
        }
    }
}
