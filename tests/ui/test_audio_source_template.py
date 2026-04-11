"""Тесты ``ui.templates.audio_source_template`` (Phase 4, ADR-016).

Покрытие:
    * Темплейт экспортирует все три фабрики контракта;
    * ``make_home_card`` возвращает :class:`SourceCard` с корректными
      данными для fake-gigaam-модуля;
    * ``make_settings_panel`` возвращает виджет, реализующий
      :class:`SettingsPanelProtocol`;
    * ``validate()`` пуст для валидной формы, непуст для пустой модели
      whisper;
    * ``apply_changes()`` записывает значения в module и speaker_map.json;
    * ``has_unsaved_changes()`` переключается при изменении поля;
    * резолвер (``core.ui_registry.resolve_template``) успешно находит
      ``audio_source`` template (интеграционный).

Все тесты помечены ``gui`` — требуют pytest-qt + Qt offscreen platform.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from core.ui_contract import SettingsPanelProtocol, UIConfig
from core.ui_registry import resolve_template
from ui.templates import audio_source_template as tmpl
from ui.templates.audio_source_template import AudioSourceState
from ui.widgets import SourceCard


# ── Fake modules ──────────────────────────────────────────────────────


class _FakeGigaAM:
    """Минимальный заместитель GigaAMSource для тестов шаблона.

    Шаблон трогает только атрибуты — никаких методов — поэтому простой
    namespace объекта достаточно, чтобы проверить apply_changes.
    """

    name = "gigaam"

    class _Variant:
        value = "rnnt"

    class _Precision:
        value = "fp32"

    def __init__(self) -> None:
        self.variant = self._Variant()
        self.precision = "fp32"
        self.device = "cpu"
        self.num_threads = 4
        self.speaker_map: dict = {}


class _FakeWhisper:
    name = "faster-whisper"

    def __init__(self) -> None:
        self.model = "large-v3"
        self.language = "ru"
        self.device = "cpu"
        self.compute_type = "int8"


# ── Session fixture ───────────────────────────────────────────────────


@pytest.fixture
def tmp_session(tmp_path: Path) -> Path:
    """Временная сессия с тремя флаками и заранее написанным speaker_map."""
    (tmp_path / "1-alice.flac").write_bytes(b"fake")
    (tmp_path / "2-bob.flac").write_bytes(b"fake")
    (tmp_path / "3-carol.flac").write_bytes(b"fake")
    # Craig-трек должен быть отфильтрован
    (tmp_path / "craig-mix.flac").write_bytes(b"fake")
    (tmp_path / "speaker_map.json").write_text(
        '{"1-alice": {"player": "Alice", "character": "Эльф", "role": "PC"}}',
        encoding="utf-8",
    )
    return tmp_path


# ── Contract exports ──────────────────────────────────────────────────


class TestContract:
    def test_template_exports_three_factories(self):
        assert callable(tmpl.make_home_card)
        assert callable(tmpl.make_runtime_panel)
        assert callable(tmpl.make_settings_panel)

    def test_resolver_finds_audio_source_template(self):
        """Resolver returns the audio_source template module.

        We compare by ``__name__`` rather than identity — another test
        (``test_core_ui_registry::TestLazyImport``) deliberately wipes
        ``ui.templates.*`` from ``sys.modules`` before exercising the
        lazy-import code path, which invalidates identity comparison
        but is otherwise benign.
        """
        cfg = UIConfig(template="audio_source")
        module = resolve_template(cfg)
        assert module.__name__ == tmpl.__name__
        assert callable(module.make_settings_panel)


# ── Home card ─────────────────────────────────────────────────────────


@pytest.mark.gui
class TestHomeCard:
    def test_home_card_returns_source_card(self, qtbot, tmp_session: Path):
        card = tmpl.make_home_card(
            parent=None,
            module=_FakeGigaAM(),
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "gigaam"},
        )
        qtbot.addWidget(card)
        assert isinstance(card, SourceCard)

    def test_home_card_craig_track_filtered(self, qtbot, tmp_session: Path):
        """Craig-треки не должны попадать в files list."""
        card = tmpl.make_home_card(
            parent=None,
            module=_FakeGigaAM(),
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "gigaam"},
        )
        qtbot.addWidget(card)
        # внутри SourceCardData files-кортеж
        data = card._data  # noqa: SLF001 — тест-friend
        assert all("craig" not in name.lower() for name in data.files)

    def test_home_card_without_session_shows_warning(self, qtbot):
        card = tmpl.make_home_card(
            parent=None,
            module=_FakeGigaAM(),
            state=AudioSourceState(session_dir=None),
            params={"backend": "gigaam"},
        )
        qtbot.addWidget(card)
        assert card._data.status == "warning"  # noqa: SLF001


# ── Settings panel ────────────────────────────────────────────────────


@pytest.mark.gui
class TestSettingsPanel:
    def test_panel_implements_protocol(self, qtbot, tmp_session: Path):
        panel = tmpl.make_settings_panel(
            parent=None,
            module=_FakeGigaAM(),
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "gigaam"},
        )
        qtbot.addWidget(panel)
        assert isinstance(panel, SettingsPanelProtocol)

    def test_validate_empty_for_valid_gigaam(self, qtbot, tmp_session: Path):
        panel = tmpl.make_settings_panel(
            parent=None,
            module=_FakeGigaAM(),
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "gigaam"},
        )
        qtbot.addWidget(panel)
        assert panel.validate() == []

    def test_validate_catches_empty_whisper_model(self, qtbot, tmp_session: Path):
        fake = _FakeWhisper()
        fake.model = ""
        panel = tmpl.make_settings_panel(
            parent=None,
            module=fake,
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "whisper"},
        )
        qtbot.addWidget(panel)
        errors = panel.validate()
        assert any("Модель" in e for e in errors)

    def test_validate_catches_bad_language(self, qtbot, tmp_session: Path):
        fake = _FakeWhisper()
        fake.language = "russian"  # не 2 символа
        panel = tmpl.make_settings_panel(
            parent=None,
            module=fake,
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "whisper"},
        )
        qtbot.addWidget(panel)
        errors = panel.validate()
        assert any("ISO" in e or "язык" in e.lower() for e in errors)

    def test_apply_changes_writes_device(self, qtbot, tmp_session: Path):
        fake = _FakeGigaAM()
        panel = tmpl.make_settings_panel(
            parent=None,
            module=fake,
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "gigaam"},
        )
        qtbot.addWidget(panel)

        panel._device_combo.setCurrentIndex(1)  # noqa: SLF001 — cpu→cuda
        panel.apply_changes()

        assert fake.device == "cuda"

    def test_apply_changes_writes_speaker_map(
        self, qtbot, tmp_session: Path
    ):
        panel = tmpl.make_settings_panel(
            parent=None,
            module=_FakeGigaAM(),
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "gigaam"},
        )
        qtbot.addWidget(panel)

        # Меняем Player для первой строки
        panel._speakers_table.item(0, 0).setText("NewName")  # noqa: SLF001
        panel.apply_changes()

        from core.speaker_map import load_speaker_map_raw

        on_disk = load_speaker_map_raw(tmp_session)
        # Таблица заполнена через iter(_input_files); первой идёт
        # 1-alice (sorted по имени)
        first_key = next(iter(panel._speakers_row_keys))  # noqa: SLF001
        assert on_disk[first_key]["player"] == "NewName"

    def test_has_unsaved_changes_toggles(self, qtbot, tmp_session: Path):
        panel = tmpl.make_settings_panel(
            parent=None,
            module=_FakeGigaAM(),
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "gigaam"},
        )
        qtbot.addWidget(panel)

        assert panel.has_unsaved_changes() is False

        panel._threads_spin.setValue(8)  # noqa: SLF001
        assert panel.has_unsaved_changes() is True

        panel.apply_changes()
        assert panel.has_unsaved_changes() is False

    def test_changed_signal_fires_on_field_edit(
        self, qtbot, tmp_session: Path
    ):
        panel = tmpl.make_settings_panel(
            parent=None,
            module=_FakeGigaAM(),
            state=AudioSourceState(session_dir=tmp_session),
            params={"backend": "gigaam"},
        )
        qtbot.addWidget(panel)

        with qtbot.waitSignal(panel.changed, timeout=1000):
            panel._threads_spin.setValue(8)  # noqa: SLF001
