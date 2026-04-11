"""audio_source_template — UI-шаблон для speech-модулей (GigaAM / Whisper).

Реализует Module UI Contract из ADR-016 §Template contract. Экспортирует
три фабрики виджетов:

    make_home_card(parent, module, state, params) -> QWidget
    make_settings_panel(parent, module, state, params) -> QWidget
    make_runtime_panel(parent, module, state, params) -> QWidget

Шаблон делит контракт между двумя backend'ами: GigaAMSource и
FasterWhisperSource. Разница — ``params`` из ``module.ui_config.params``:

    - GigaAM:  params={"backend": "gigaam", "variant": "rnnt", ...}
    - Whisper: params={"backend": "whisper", "model": "large-v3", ...}

Settings panel рендерит одну форму с блоками:

    1. Входные файлы (read-only) — список .flac / .wav из session_dir
    2. Участники — таблица speaker_map (stem → player / character / role)
    3. Движок — precision (fp32/int8 для gigaam) или model + language
       (для whisper)
    4. Hotwords — read-only preview (в Phase 4 не редактируется; план —
       PR в Phase ≥ 10)
    5. Advanced — device (cpu/cuda), num_threads (collapsible)

Форма реализует ``core.ui_contract.SettingsPanelProtocol``: ``changed``
сигнал на каждое поле, ``validate()`` / ``apply_changes()`` /
``has_unsaved_changes()``. Host (``ui.shell.settings_drawer``) сам
отрисовывает header/footer drawer'а.

Шаблон НЕ импортирует ``sources/*`` — он знает только о ``module`` как о
``Any``-объекте с известными атрибутами. Это позволяет ему работать с
обеими backend'ами без cross-import-а.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.speaker_map import load_speaker_map_raw, save_speaker_map_raw
from ui.shell import theme
from ui.widgets import SourceCard, SourceCardData

logger = logging.getLogger(__name__)

_AUDIO_EXTENSIONS: tuple[str, ...] = (".flac", ".wav", ".mp3", ".ogg", ".m4a", ".opus")
_ROLE_OPTIONS: tuple[str, ...] = ("PC", "GM", "NPC", "Зритель")
_GIGAAM_PRECISION_OPTIONS: tuple[tuple[str, str], ...] = (
    ("fp32", "FP32 (~900 MB, точнее)"),
    ("int8", "INT8 (~250 MB, быстрее)"),
)
_DEVICE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("cpu", "CPU"),
    ("cuda", "CUDA (GPU)"),
)


# ── Runtime state, прокидываемый хостом ────────────────────────────────


@dataclass
class AudioSourceState:
    """Снэпшот runtime-состояния для фабрик аудио-шаблона.

    Хост собирает это при каждом вызове фабрики. В Phase 3-4 всё ещё
    можно передать пустой state (``AudioSourceState()``) — шаблон
    отрендерит «нет session_dir» сообщение.

    Аттрибуты:
        session_dir: папка текущей сессии; используется для сканирования
            входных файлов и загрузки/сохранения ``speaker_map.json``.
        progress_by_track: (Phase 6+) соответствует runtime-прогрессу;
            пока не используется фабриками, но поле зарезервировано.
    """

    session_dir: Path | None = None
    progress_by_track: dict[str, float] = field(default_factory=dict)


# ── Public factory functions ───────────────────────────────────────────


def make_home_card(
    parent: QWidget | None,
    module: Any,
    state: AudioSourceState | None,
    params: dict[str, Any],
) -> QWidget:
    """Карточка в блоке 1 (idle view).

    Собирает ``SourceCardData`` из состояния и возвращает :class:`SourceCard`.
    В Phase 3 эта функция не вызывается (карточки там создаются с
    фикстурой прямо в ``app.py``); с Phase 5 — это канонический путь.
    """
    backend = _backend_from_params(params)
    title, subtitle = _title_and_subtitle(module, backend, params)

    files: tuple[str, ...] = ()
    if state is not None and state.session_dir is not None:
        files = _scan_audio_files(state.session_dir)

    data = SourceCardData(
        title=title,
        subtitle=subtitle,
        files=files,
        files_hint="",
        status="ready" if files else "warning",
        status_text="готов" if files else "нужны файлы",
    )
    return SourceCard(data, parent=parent)


def make_settings_panel(
    parent: QWidget | None,
    module: Any,
    state: AudioSourceState | None,
    params: dict[str, Any],
) -> "AudioSourceSettingsPanel":
    """Форма настроек для drawer'а.

    Host (SettingsDrawer) обернёт результат в QScrollArea и нарисует
    sticky header/footer сам. Возвращённый виджет реализует
    ``SettingsPanelProtocol``.
    """
    return AudioSourceSettingsPanel(
        module=module,
        state=state or AudioSourceState(),
        params=params,
        parent=parent,
    )


def make_runtime_panel(
    parent: QWidget | None,
    module: Any,
    state: AudioSourceState | None,
    params: dict[str, Any],
) -> QWidget:
    """Панель для блока 3 (runtime view).

    В Phase 4 — читаемый stub. Полная реализация с per-track progress
    приезжает в Phase 6, когда появится ``QThread`` worker и сигналы.
    """
    backend = _backend_from_params(params)
    label_text = {
        "gigaam": "Аудио · GigaAM-v3",
        "whisper": "Аудио · faster-whisper",
    }.get(backend, "Аудио")

    w = QWidget(parent)
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(theme.GAP_SMALL_PX)

    title = QLabel(label_text, w)
    title.setStyleSheet(
        f"color: {theme.COLOR_FOREGROUND}; "
        f"font-size: {theme.FONT_SIZE_H3_PX}px;"
    )
    layout.addWidget(title)

    hint = QLabel("Runtime panel (per-track progress) — Phase 6", w)
    hint.setStyleSheet(
        f"color: {theme.COLOR_MUTED_FG}; font-size: {theme.FONT_SIZE_MICRO_PX}px;"
    )
    layout.addWidget(hint)
    layout.addStretch(1)
    return w


# ── Settings panel implementation ─────────────────────────────────────


class AudioSourceSettingsPanel(QWidget):
    """Форма настроек аудио-источника.

    Реализует ``SettingsPanelProtocol``:
        - ``changed`` — Qt ``Signal`` без аргументов, эмитится при любом
          изменении любого поля;
        - ``validate()`` — возвращает список ошибок (непустой = блокирует save);
        - ``apply_changes()`` — записывает значения в ``module`` и
          (если есть session_dir) в ``session_dir/speaker_map.json``;
        - ``has_unsaved_changes()`` — сравнение текущего состояния с baseline.

    Baseline снимается в конструкторе и после каждого ``apply_changes``.
    """

    changed = Signal()

    def __init__(
        self,
        *,
        module: Any,
        state: AudioSourceState,
        params: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._module = module
        self._state = state
        self._params = params
        self._backend = _backend_from_params(params)

        # ── Loaded data ──────────────────────────────────────────────
        self._speaker_map_raw: dict[str, dict[str, str]] = {}
        if state.session_dir is not None:
            try:
                self._speaker_map_raw = load_speaker_map_raw(state.session_dir)
            except Exception:  # noqa: BLE001 — best-effort в UI
                logger.warning(
                    "Failed to load speaker_map from %s", state.session_dir
                )
        self._input_files: tuple[str, ...] = ()
        if state.session_dir is not None:
            self._input_files = _scan_audio_files(state.session_dir)

        # ── Baseline (для has_unsaved_changes) ───────────────────────
        self._baseline: dict[str, Any] = {}

        # ── Build form ───────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.GAP_LARGE_PX)

        root.addWidget(self._build_files_section())
        root.addWidget(self._build_speakers_section())
        root.addWidget(self._build_engine_section())
        root.addWidget(self._build_hotwords_section())
        root.addWidget(self._build_advanced_section())
        root.addStretch(1)

        # Wire any remaining signals that need baseline to be ready,
        # then snapshot baseline.
        self._snapshot_baseline()

    # ── Section builders ─────────────────────────────────────────────

    def _build_files_section(self) -> QWidget:
        box = _SectionBox("Входные файлы", parent=self)

        if not self._input_files:
            empty = QLabel("Нет аудиофайлов в папке сессии.", box)
            empty.setStyleSheet(
                f"color: {theme.COLOR_MUTED_FG}; "
                f"font-size: {theme.FONT_SIZE_SMALL_PX}px;"
            )
            box.add(empty)
            return box

        for name in self._input_files:
            row = QLabel(f"📄  {name}", box)
            row.setStyleSheet(
                f"color: {theme.COLOR_FOREGROUND}; "
                f"font-family: Consolas, 'Courier New', monospace; "
                f"font-size: {theme.FONT_SIZE_SMALL_PX}px;"
            )
            box.add(row)

        hint = QLabel(
            f"Всего дорожек: {len(self._input_files)}", box
        )
        hint.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        box.add(hint)
        return box

    def _build_speakers_section(self) -> QWidget:
        box = _SectionBox("Участники", parent=self)

        if not self._input_files:
            empty = QLabel(
                "Список участников появится после добавления аудиофайлов.",
                box,
            )
            empty.setStyleSheet(
                f"color: {theme.COLOR_MUTED_FG}; "
                f"font-size: {theme.FONT_SIZE_SMALL_PX}px;"
            )
            box.add(empty)
            return box

        table = QTableWidget(len(self._input_files), 3, box)
        table.setHorizontalHeaderLabels(["Игрок", "Персонаж", "Роль"])
        table.verticalHeader().setVisible(True)
        table.verticalHeader().setDefaultSectionSize(32)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.SelectedClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {theme.COLOR_CARD};
                border: 1px solid {theme.COLOR_BORDER};
                border-radius: {theme.RADIUS_CARD_PX}px;
                gridline-color: {theme.COLOR_BORDER};
                font-size: {theme.FONT_SIZE_SMALL_PX}px;
            }}
            QHeaderView::section {{
                background-color: {theme.COLOR_SECONDARY};
                color: {theme.COLOR_MUTED_FG};
                border: none;
                padding: 6px 8px;
                font-size: {theme.FONT_SIZE_MICRO_PX}px;
            }}
            """
        )
        vlabels = []
        for row_idx, stem in enumerate(self._input_files):
            stem_key = Path(stem).stem
            entry = self._speaker_map_raw.get(stem_key, {})
            player = QTableWidgetItem(entry.get("player", ""))
            character = QTableWidgetItem(entry.get("character", ""))
            role_cell = QComboBox(table)
            role_cell.addItems(_ROLE_OPTIONS)
            role_cell.setCurrentText(entry.get("role", "PC"))
            role_cell.currentIndexChanged.connect(self.changed.emit)

            table.setItem(row_idx, 0, player)
            table.setItem(row_idx, 1, character)
            table.setCellWidget(row_idx, 2, role_cell)
            vlabels.append(stem_key)
        table.setVerticalHeaderLabels(vlabels)
        table.itemChanged.connect(lambda _item: self.changed.emit())

        self._speakers_table = table
        self._speakers_row_keys = tuple(vlabels)
        box.add(table)
        return box

    def _build_engine_section(self) -> QWidget:
        box = _SectionBox("Движок", parent=self)
        if self._backend == "gigaam":
            self._precision_combo = QComboBox(box)
            for value, label in _GIGAAM_PRECISION_OPTIONS:
                self._precision_combo.addItem(label, userData=value)
            current = getattr(self._module, "precision", None)
            current_value = getattr(current, "value", current) or "fp32"
            idx = next(
                (
                    i
                    for i, (v, _) in enumerate(_GIGAAM_PRECISION_OPTIONS)
                    if v == current_value
                ),
                0,
            )
            self._precision_combo.setCurrentIndex(idx)
            self._precision_combo.currentIndexChanged.connect(self.changed.emit)
            box.add(_form_row("Precision:", self._precision_combo, parent=box))

            variant_label = QLabel(
                "Вариант: RNNT (по умолчанию)", box
            )
            variant_label.setStyleSheet(
                f"color: {theme.COLOR_MUTED_FG}; "
                f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
            )
            box.add(variant_label)
        else:  # whisper
            self._model_edit = QLineEdit(box)
            self._model_edit.setText(
                str(getattr(self._module, "model", ""))
                or "bzikst/faster-whisper-large-v3-ru-podlodka"
            )
            self._model_edit.textChanged.connect(self.changed.emit)
            box.add(_form_row("Модель:", self._model_edit, parent=box))

            self._language_edit = QLineEdit(box)
            self._language_edit.setText(
                str(getattr(self._module, "language", "ru"))
            )
            self._language_edit.textChanged.connect(self.changed.emit)
            box.add(_form_row("Язык:", self._language_edit, parent=box))
        return box

    def _build_hotwords_section(self) -> QWidget:
        box = _SectionBox("Hotwords (read-only)", parent=self)
        hint = QLabel(
            "Редактирование hotwords появится в следующей версии. "
            "Сейчас используется встроенный TTRPG-словарь GigaAM bundle.",
            box,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_MICRO_PX}px;"
        )
        box.add(hint)
        return box

    def _build_advanced_section(self) -> QWidget:
        box = _SectionBox("Дополнительно", parent=self)

        # Device
        self._device_combo = QComboBox(box)
        for value, label in _DEVICE_OPTIONS:
            self._device_combo.addItem(label, userData=value)
        current_device = getattr(self._module, "device", "cpu") or "cpu"
        idx = next(
            (i for i, (v, _) in enumerate(_DEVICE_OPTIONS) if v == current_device),
            0,
        )
        self._device_combo.setCurrentIndex(idx)
        self._device_combo.currentIndexChanged.connect(self.changed.emit)
        box.add(_form_row("Устройство:", self._device_combo, parent=box))

        # num_threads (gigaam only)
        if self._backend == "gigaam":
            self._threads_spin = QSpinBox(box)
            self._threads_spin.setRange(1, 32)
            self._threads_spin.setValue(
                int(getattr(self._module, "num_threads", 4) or 4)
            )
            self._threads_spin.valueChanged.connect(self.changed.emit)
            box.add(_form_row("Потоки CPU:", self._threads_spin, parent=box))
        else:
            # faster-whisper: compute_type
            self._compute_combo = QComboBox(box)
            for value in ("float16", "int8_float16", "int8", "float32"):
                self._compute_combo.addItem(value, userData=value)
            current = getattr(self._module, "compute_type", "float16") or "float16"
            idx = self._compute_combo.findData(current)
            if idx >= 0:
                self._compute_combo.setCurrentIndex(idx)
            self._compute_combo.currentIndexChanged.connect(self.changed.emit)
            box.add(_form_row("Compute type:", self._compute_combo, parent=box))

        return box

    # ── SettingsPanelProtocol ────────────────────────────────────────

    def validate(self) -> list[str]:
        """Проверка формы.

        Правила:
            * whisper: язык должен быть 2 символа (код ISO 639-1).
            * whisper: модель не должна быть пустой.
            * gigaam: без дополнительных правил.
        """
        errors: list[str] = []
        if self._backend == "whisper":
            if not self._model_edit.text().strip():
                errors.append("Модель не должна быть пустой.")
            lang = self._language_edit.text().strip()
            if lang and len(lang) != 2:
                errors.append(
                    f"Код языка должен быть 2 символа ISO 639-1, получено: {lang!r}"
                )
        return errors

    def apply_changes(self) -> None:
        """Записать значения формы в ``module`` и speaker_map на диск."""
        # ── Engine ───────────────────────────────────────────────────
        if self._backend == "gigaam":
            precision = self._precision_combo.currentData()
            if precision is not None:
                self._apply_module_attr("precision", precision)
            device = self._device_combo.currentData()
            self._apply_module_attr("device", device)
            self._apply_module_attr("num_threads", self._threads_spin.value())
        else:
            self._apply_module_attr("model", self._model_edit.text().strip())
            self._apply_module_attr(
                "language", self._language_edit.text().strip() or "ru"
            )
            device = self._device_combo.currentData()
            self._apply_module_attr("device", device)
            compute_type = self._compute_combo.currentData()
            self._apply_module_attr("compute_type", compute_type)

        # ── Speaker map ──────────────────────────────────────────────
        new_map: dict[str, dict[str, str]] = {}
        if getattr(self, "_speakers_table", None) is not None:
            table = self._speakers_table
            for row_idx, stem_key in enumerate(self._speakers_row_keys):
                player_item = table.item(row_idx, 0)
                character_item = table.item(row_idx, 1)
                role_widget = table.cellWidget(row_idx, 2)
                entry = {
                    "player": player_item.text() if player_item else "",
                    "character": character_item.text() if character_item else "",
                    "role": (
                        role_widget.currentText()
                        if isinstance(role_widget, QComboBox)
                        else "PC"
                    ),
                }
                new_map[stem_key] = entry
            self._speaker_map_raw = new_map

            if self._state.session_dir is not None:
                try:
                    save_speaker_map_raw(self._state.session_dir, new_map)
                except OSError:
                    logger.exception("Failed to save speaker_map")

        self._snapshot_baseline()

    def has_unsaved_changes(self) -> bool:
        return self._current_snapshot() != self._baseline

    # ── Helpers ──────────────────────────────────────────────────────

    def _apply_module_attr(self, name: str, value: Any) -> None:
        """setattr на модуль, если атрибут есть. Иначе просто игнорим.

        Это защищает нас от ситуации «шаблон знает про новое поле, а
        модуль на старой версии его ещё не поддерживает» — безопаснее
        пропустить, чем упасть.
        """
        if hasattr(self._module, name):
            try:
                setattr(self._module, name, value)
            except (AttributeError, TypeError):
                logger.warning(
                    "Could not setattr %s on %s", name, type(self._module).__name__
                )

    def _snapshot_baseline(self) -> None:
        self._baseline = self._current_snapshot()

    def _current_snapshot(self) -> dict[str, Any]:
        """Собрать сериализуемый снимок состояния формы для diff'а."""
        snap: dict[str, Any] = {
            "device": self._device_combo.currentData(),
        }
        if self._backend == "gigaam":
            snap["precision"] = self._precision_combo.currentData()
            snap["num_threads"] = self._threads_spin.value()
        else:
            snap["model"] = self._model_edit.text().strip()
            snap["language"] = self._language_edit.text().strip()
            snap["compute_type"] = self._compute_combo.currentData()

        if getattr(self, "_speakers_table", None) is not None:
            rows = []
            for row_idx, stem_key in enumerate(self._speakers_row_keys):
                player_item = self._speakers_table.item(row_idx, 0)
                character_item = self._speakers_table.item(row_idx, 1)
                role_widget = self._speakers_table.cellWidget(row_idx, 2)
                rows.append(
                    (
                        stem_key,
                        player_item.text() if player_item else "",
                        character_item.text() if character_item else "",
                        role_widget.currentText()
                        if isinstance(role_widget, QComboBox)
                        else "PC",
                    )
                )
            snap["speakers"] = tuple(rows)
        return snap


# ── Small helpers ──────────────────────────────────────────────────────


class _SectionBox(QFrame):
    """Тонкая рамка с заголовком — визуальный контейнер секции формы."""

    def __init__(self, title: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.GAP_SMALL_PX)

        label = QLabel(title.upper(), self)
        label.setStyleSheet(
            f"color: {theme.COLOR_MUTED_FG}; "
            f"font-size: {theme.FONT_SIZE_TINY_PX}px; "
            f"letter-spacing: 1px;"
        )
        root.addWidget(label)
        self._content_layout = root

    def add(self, widget: QWidget) -> None:
        self._content_layout.addWidget(widget)


def _form_row(label_text: str, field: QWidget, *, parent: QWidget) -> QWidget:
    """Горизонтальный ряд «Лейбл: [field]»."""
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(theme.GAP_SMALL_PX)
    label = QLabel(label_text, row)
    label.setStyleSheet(
        f"color: {theme.COLOR_FOREGROUND}; "
        f"font-size: {theme.FONT_SIZE_SMALL_PX}px;"
    )
    label.setFixedWidth(120)
    layout.addWidget(label)
    layout.addWidget(field, stretch=1)
    return row


def _backend_from_params(params: dict[str, Any]) -> str:
    """Определить backend из params; default — ``gigaam``."""
    backend = str(params.get("backend", "gigaam")).lower()
    if backend not in ("gigaam", "whisper"):
        return "gigaam"
    return backend


def _title_and_subtitle(
    module: Any, backend: str, params: dict[str, Any]
) -> tuple[str, str]:
    if backend == "gigaam":
        variant = getattr(module, "variant", None)
        variant_label = getattr(variant, "value", variant) or "rnnt"
        return ("Аудио", f"GigaAM-v3 {variant_label.upper()} · русский")
    # whisper
    model = str(getattr(module, "model", "")) or "faster-whisper"
    language = str(getattr(module, "language", "")) or "многоязычная"
    return ("Аудио", f"{model} · {language}")


def _scan_audio_files(session_dir: Path) -> tuple[str, ...]:
    """Найти аудио-файлы в папке сессии, отсортированные по имени."""
    if not session_dir.exists():
        return ()
    names: list[str] = []
    try:
        for entry in sorted(session_dir.iterdir()):
            if entry.is_file() and entry.suffix.lower() in _AUDIO_EXTENSIONS:
                if entry.stem.lower().startswith("craig"):
                    continue
                names.append(entry.name)
    except OSError:
        return ()
    return tuple(names)
