import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App.Theme
import "screens"

// Root shell: fixed-width Sidebar on the left, switchable screen on
// the right driven by `appModel.screen` (context property from Python).
//
// The four screens are peers — use StackLayout (show/hide by index),
// not StackView (push/pop), so state is preserved across nav toggles.
ApplicationWindow {
    id: window
    visible: true
    width: 1280
    height: 800
    minimumWidth: 960
    minimumHeight: 620
    title: qsTr("Session Transcriber")
    color: Theme.bg

    // Screen name → index in the StackLayout below. Kept in sync with
    // the order of child screens. `empty` and `timeline` share index 1:
    // the Sessions nav group shows EmptyScreen when no session exists,
    // TimelineScreen otherwise. For this foundation slice we route
    // both to TimelineScreen — the empty-state switch is wired in the
    // shell step that adds real session data.
    function screenIndex(name) {
        switch (name) {
            case "empty":    return 0
            case "timeline": return 1
            case "models":   return 2
            case "settings": return 3
            default:         return 1
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            Layout.fillHeight: true
            currentScreen: appModel.screen
            onNavigate: (screen) => appModel.screen = screen
        }

        StackLayout {
            Layout.fillHeight: true
            Layout.fillWidth: true
            currentIndex: window.screenIndex(appModel.screen)

            EmptyScreen    { }
            TimelineScreen { }
            ModelsScreen   { }
            SettingsScreen { }
        }
    }
}
