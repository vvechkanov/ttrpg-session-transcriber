# React → PySide6/QML Mapping

A cross-reference for porting the `Session Transcriber.html` prototype to PySide6 + QML on top of the existing Python codebase.

## Project layout (suggested)

```
ttrpg-session-transcriber/
├── app.py                      # QApplication, QQmlApplicationEngine, registers models
├── core/                       # existing backend (ASR, merger, parsers) — unchanged
│   ├── asr.py
│   ├── merger.py
│   ├── parsers/
│   └── ...
├── ui/
│   ├── models/                 # Q_PROPERTY wrappers, QAbstractListModel subclasses
│   │   ├── app_model.py
│   │   ├── session_model.py
│   │   ├── track_list_model.py
│   │   ├── source_list_model.py
│   │   ├── model_registry.py
│   │   └── merger_settings.py
│   ├── engines/                # QThread wrappers around core/
│   │   ├── asr_worker.py
│   │   └── merger_worker.py
│   └── qml/
│       ├── Main.qml            # root window, StackLayout over screens
│       ├── Theme.qml           # singleton with color/typography tokens
│       ├── Sidebar.qml
│       ├── screens/
│       │   ├── EmptyScreen.qml
│       │   ├── TimelineScreen.qml
│       │   ├── ModelsScreen.qml
│       │   ├── SettingsScreen.qml
│       │   └── SessionSettingsPage.qml
│       ├── timeline/
│       │   ├── PhaseBar.qml
│       │   ├── Ruler.qml
│       │   ├── SourceRow.qml
│       │   ├── TrackRow.qml          # waveform + avatar + model badge
│       │   ├── WaveformCanvas.qml    # Canvas painting
│       │   ├── StitchOverlay.qml
│       │   └── MergerChip.qml
│       ├── dialogs/
│       │   ├── AddSourceDialog.qml
│       │   └── AddTrackDialog.qml
│       ├── drawers/
│       │   └── ModelDetailsDrawer.qml
│       ├── popovers/
│       │   └── TrackOverridePopover.qml
│       └── controls/
│           ├── PrimaryButton.qml
│           ├── GhostButton.qml
│           ├── Segmented.qml
│           ├── ModelPicker.qml
│           └── Chip.qml
└── resources.qrc
```

## Component cross-reference

| React (prototype)          | QML                              | Notes |
|----------------------------|----------------------------------|-------|
| `<App>` + screen switch    | `ApplicationWindow` + `StackLayout` bound to `appModel.screen` | Use `StackLayout` not `StackView` — screens are peers, not pushed/popped |
| `<AppSidebar>`             | `Sidebar.qml` w/ `ListView`      | Use a `ListModel` for nav items + `delegate` for each |
| `<EmptyState>`             | `EmptyScreen.qml`                | Static layout, one `Column` w/ centered alignment |
| `<TimelineCanvas>`         | `TimelineScreen.qml`             | Root container; composes PhaseBar + Ruler + SourceRow(×N) + TrackRow(×N) |
| `<Ruler>`                  | `Ruler.qml`                      | `Canvas` + `onPaint` drawing tick marks from bound duration |
| `<TrackRow>`               | `TrackRow.qml`                   | `RowLayout` { Avatar + Labels + ModelBadge + WaveformCanvas } |
| `<WaveformLane>` (SVG)     | `WaveformCanvas.qml`             | `Canvas` painting peaks from `track.peaks` (Float32Array equivalent); repaint on `progressChanged` to show ASR overlay |
| `<MergeStitches>`          | `StitchOverlay.qml`              | Absolutely positioned `Repeater` of vertical lines; animate opacity in when phase==="merge" |
| `<ModelsScreen>`           | `ModelsScreen.qml`               | `ListView` with `model: modelRegistry` + delegate row; click opens drawer |
| `<ModelDetailsDrawer>`     | `ModelDetailsDrawer.qml`         | Use Qt Quick Controls `Drawer` with `edge: Qt.RightEdge` |
| `<TrackOverridePopover>`   | `TrackOverridePopover.qml`       | Qt Quick `Popup` anchored to the badge item |
| `<SessionScreen>` tabs     | `TabBar` + `StackLayout`         | Tabs drive `currentIndex` of a `StackLayout` containing 4 panes |
| `<SessionSettings>`        | `SessionSettingsPage.qml`        | Two scroll sections: players table + merger form |
| `<AddSourceDialog>`        | `AddSourceDialog.qml`            | Qt Quick Controls `Dialog` with custom content |
| `<Btn variant="primary">`  | `PrimaryButton.qml`              | Thin wrapper around `Button` w/ styling overrides |
| `<Btn variant="ghost">`    | `GhostButton.qml`                |  |
| `<Segmented>`              | `Segmented.qml`                  | `Row` of `Button`s w/ shared `ButtonGroup` |
| Inline `style={{...}}`     | Inline QML props + `Theme.*`     | See Theme section below |
| React state `useState`     | `property` declarations          | Local state for UI-only things (popover open, etc.) |
| State from backend         | Q_PROPERTY on exposed objects    | Session data, track data, merger settings |
| `useEffect` w/ listener    | `Connections` element            | Listen to signals from Python models |
| `localStorage` persist     | `QSettings`                      | For last-opened session, window size, etc. |

## Theme singleton

Create a QML singleton so tokens are referenced as `Theme.accent`, `Theme.ink`, etc.

```qml
// ui/qml/Theme.qml
pragma Singleton
import QtQuick

QtObject {
    readonly property color bg:        "#FAF8F5"
    readonly property color card:      "#FFFFFF"
    readonly property color cardAlt:   "#F4F0E8"

    readonly property color ink:       "#2D2520"
    readonly property color ink2:      "#4A3F36"
    readonly property color ink3:      "#6B625A"
    readonly property color ink4:      "#9A9088"

    readonly property color border:     Qt.rgba(107/255, 98/255, 90/255, 0.18)
    readonly property color borderSoft: Qt.rgba(107/255, 98/255, 90/255, 0.10)

    readonly property color accent:     "#C97B3E"
    readonly property color accentDeep: "#9A5A28"
    readonly property color accentSoft: Qt.rgba(201/255, 123/255, 62/255, 0.35)
    readonly property color accentWash: Qt.rgba(201/255, 123/255, 62/255, 0.08)

    readonly property color green:      "#6B8E4E"
    readonly property color red:        "#B45454"
    readonly property color amber:      "#C89A3E"

    readonly property string fontSans:  "Inter, Segoe UI, system-ui, sans-serif"
    readonly property string fontMono:  "JetBrains Mono, Fira Code, Menlo, monospace"

    readonly property int radiusSm: 6
    readonly property int radiusMd: 9
    readonly property int radiusLg: 12
}
```

Register in `app.py`:

```python
qmlRegisterSingletonType("App.Theme", 1, 0, "Theme", "qrc:/qml/Theme.qml")
```

## Data models from Python → QML

### Simple Q_PROPERTY (scalars)

```python
# ui/models/app_model.py
from PySide6.QtCore import QObject, Property, Signal

class AppModel(QObject):
    screenChanged = Signal()
    phaseChanged = Signal()

    def __init__(self):
        super().__init__()
        self._screen = "timeline"
        self._phase = "idle"

    @Property(str, notify=screenChanged)
    def screen(self): return self._screen

    @screen.setter
    def screen(self, v):
        if self._screen != v:
            self._screen = v
            self.screenChanged.emit()

    # same for phase
```

Expose:

```python
engine = QQmlApplicationEngine()
app_model = AppModel()
engine.rootContext().setContextProperty("appModel", app_model)
```

Use in QML:

```qml
StackLayout {
    currentIndex: ["empty","timeline","models","settings"].indexOf(appModel.screen)
}
```

### List model (tracks, sources, installed models)

Subclass `QAbstractListModel`. Example for tracks:

```python
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

class TrackListModel(QAbstractListModel):
    NameRole     = Qt.UserRole + 1
    CharsRole    = Qt.UserRole + 2
    ModelIdRole  = Qt.UserRole + 3
    PeaksRole    = Qt.UserRole + 4
    ProgressRole = Qt.UserRole + 5

    def roleNames(self):
        return {
            self.NameRole:     b"name",
            self.CharsRole:    b"characters",
            self.ModelIdRole:  b"modelId",
            self.PeaksRole:    b"peaks",
            self.ProgressRole: b"progress",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._tracks)

    def data(self, index, role):
        t = self._tracks[index.row()]
        if role == self.NameRole:     return t.name
        if role == self.CharsRole:    return t.characters
        if role == self.ModelIdRole:  return t.model_id
        if role == self.PeaksRole:    return t.peaks
        if role == self.ProgressRole: return t.progress
        return None

    def setProgress(self, row, pct):
        self._tracks[row].progress = pct
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [self.ProgressRole])
```

In QML:

```qml
ListView {
    model: trackList            // context-property from Python
    delegate: TrackRow {
        playerName:  name
        characters:  characters
        modelId:     modelId
        peaks:       peaks
        progress:    progress
    }
}
```

## Threading (critical — don't skip)

The ASR and merger engines are CPU-heavy. Running them on the main Qt thread will freeze the UI (including the phase-bar animation). Use QThread + worker pattern:

```python
from PySide6.QtCore import QObject, Signal, QThread

class AsrWorker(QObject):
    progress = Signal(float)       # 0..1
    done     = Signal(list)        # segments
    error    = Signal(str)

    def __init__(self, track_path, model_id, params):
        super().__init__()
        # ...

    def run(self):
        try:
            # call existing core/asr.py, emit progress on each chunk
            for pct, partial in asr.transcribe_streaming(...):
                self.progress.emit(pct)
            self.done.emit(final_segments)
        except Exception as e:
            self.error.emit(str(e))

# orchestrator (per-track parallel)
def start_asr(track, model_id, params):
    thread = QThread()
    worker = AsrWorker(track.path, model_id, params)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.progress.connect(lambda p: trackList.setProgress(track.row, p))
    worker.done.connect(lambda segs: on_asr_done(track, segs))
    worker.done.connect(thread.quit)
    thread.start()
    return thread  # keep reference
```

For `torch` / `faster-whisper`: each worker loads its own model instance unless you share across threads carefully. Simpler: load once, serialize track processing. Parallelism for ASR is usually not worth the RAM cost for local use.

## Specific non-obvious bits

### Waveform canvas

The prototype fakes waveforms with random bars. Real impl:

1. After import, decode audio (ffmpeg, or torchaudio) to mono float32
2. Compute peaks: take `max(abs(x))` per N-sample chunk to get ~2000 peak values per track
3. Cache peaks per track (`.peaks.bin` next to the audio file, or in session DB)
4. Pass `list[float]` to QML via Q_PROPERTY or list-model role
5. In `WaveformCanvas.qml` (`Canvas { onPaint }`), iterate peaks, draw vertical bars centered on y=h/2
6. For ASR overlay, draw a second pass with the tinted color up to `progress * width`

### Stitch overlay

Vertical markers across all tracks showing where the merger is bridging gaps. Position is absolute in timeline coords → convert to x-pixel using the same `durationToX()` the ruler uses. Stagger the fade-in: `NumberAnimation { duration: 180; delay: index * 60 }`.

### Per-track model override popover anchoring

Qt's `Popup` can be anchored to a specific item using `x`/`y` relative to its parent, or via `popup.open()` with prior positioning. Keep the popover non-modal so the user can still see the timeline underneath.

### Drawer from right edge

```qml
Drawer {
    id: modelDrawer
    edge: Qt.RightEdge
    width: 460
    height: parent.height
    modal: true
    property var model: null   // set before open()
    // content
}

// open:
modelDrawer.model = installedModels.get(row)
modelDrawer.open()
```

### Inline rename (player names, character names)

Use `TextInput` inside a `MouseArea` that switches to edit mode on double-click, commits on Enter/focus-loss, cancels on ESC.

### Segmented buttons

```qml
// Segmented.qml
Row {
    property alias model: repeater.model
    property int currentIndex: 0
    signal activated(int index)
    Repeater {
        id: repeater
        Button {
            text: modelData
            checkable: true
            checked: index === parent.currentIndex
            onClicked: { parent.currentIndex = index; parent.activated(index) }
            // custom background using Theme.accentWash etc.
        }
    }
}
```

### Animations

```qml
// Drawer slide-in handled by Drawer built-in.
// For custom popovers:
Behavior on x { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
Behavior on opacity { NumberAnimation { duration: 180 } }
```

## Recommended implementation order

1. **Theme + Main shell + Sidebar** — get navigation working between 3 empty screens
2. **ModelsScreen** with a `ListView` + drawer — simplest data flow, teaches you the Q_PROPERTY + dialog pattern
3. **EmptyScreen + Settings** — pure forms, no threading
4. **TimelineScreen idle phase** — ruler, tracks, sources, but no processing. Get the layout right.
5. **AsrWorker + progress wiring** — run one track, show progress overlay on its waveform
6. **Parallel/sequential ASR for all tracks**
7. **MergerWorker + stitch overlay**
8. **Done phase, playback, output chip**
9. **Polish:** popover, inline edits, animations

Each step should ship — you can stop at any point and have a usable app.

## Things the prototype hand-waves

- **Real audio decoding + peak caching** — not implemented; assume ffmpeg or torchaudio
- **Parser auto-detection** — the Add-source dialog "detects" by filename extension. Real impl should probe file contents (SQLite header, JSON schema, etc.)
- **Model download progress** — the prototype shows "Установить" as a simple button. Real impl needs a progress bar + cancelation + retry
- **Error states** — prototype shows only warnings (quiet mic). Real error UI for: model download failed, ASR errored mid-track, merger parse error, disk full — handle these with toast or inline error chips

## Questions to answer before starting

- Which Qt Quick Controls style to use? `Basic` gives most control; `Material`/`Universal` will fight the warm palette. **Recommend: `Basic` + custom styles.**
- Target Qt version? **Qt 6.5+** for best Qt Quick Controls + Drawer behavior.
- Bundling strategy? PyInstaller / Briefcase / Nuitka — affects model-cache path conventions
- Auto-update? Out of scope for v1
