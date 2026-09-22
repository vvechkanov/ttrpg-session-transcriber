"""``AppPreferences`` переживает перезапуск через ``QSettings``.

Файл до этого был скриптом: ``main()`` с ручными ``_assert`` и вызовом
под ``if __name__ == "__main__"``. pytest собирал из него ноль тестов,
то есть CI не исполнял ни одной из проверок ниже. Хуже: за блоком
``__main__`` лежала функция ``_renderer_round_trip`` с настоящими
``assert``, дописанная починкой по замечанию ревью (коммит ``c69203a``,
«fix(renderers): close the holes review found in feature #8»). Её не
собирал pytest (имя с подчёркиванием) и не звал ``main()`` — проверка не
выполнялась вообще никаким способом. Здесь она восстановлена как
``test_renderer_survives_restart``.

Изоляция сделана строже, чем в скрипте. Тот уводил ``QSettings`` в общий
``TempLocation`` и звал ``.clear()`` — то есть чистил тот же INI, в
который смотрит ``tests/ui_qml_smoke/test_settings_screen_promises.py``.
Здесь хранилище уводится в собственный ``tmp_path`` теста и путь
возвращается на место после него.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtGui import QGuiApplication

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ui.models.app_preferences import AppPreferences, _to_bool  # noqa: E402


def _ensure_app() -> QGuiApplication:
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    app = QGuiApplication(sys.argv or [""])
    app.setApplicationName("Session Transcriber")
    app.setOrganizationName("Session Transcriber")
    return app


@pytest.fixture()
def scratch_settings(tmp_path: Path):
    """Увести INI ``AppPreferences`` в отдельный каталог на один тест.

    ``AppPreferences`` открывает хранилище, называя организацию и
    приложение явно, поэтому имена на ``QGuiApplication`` его никуда не
    уводят — подменять надо путь формата.
    """
    _ensure_app()
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    try:
        yield tmp_path
    finally:
        # Вернуть общий temp: соседние тесты уводят хранилище туда же
        # сами, но полагаться на порядок запуска нельзя.
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.TempLocation
            ),
        )


# Значения по умолчанию, объявленные ui/models/app_preferences.py.
# Список держится полным намеренно: настройка, добавленная без строки
# здесь, — это настройка, чей дефолт не проверяет никто.
_DEFAULTS = {
    "mergerMaxGap": "1.0",
    "mergerOocMode": "skip",
    "interfaceLanguage": "ru",
    "showTooltips": True,
    "soundOnDone": True,
    "asrDevice": "cuda",
    "asrComputeType": "float16",
    "asrBeamSize": "5",
    "asrLanguage": "ru",
    "gigaamVariant": "rnnt",
    "gigaamPrecision": "fp32",
    "asrNumThreads": "4",
    "chunkingEnabled": False,
    "chunkingChunkChars": "40000",
    "chunkingOverlapRatio": "0.20",
    "renderer": "plain-text",
}

# Значение, отличное от дефолта, для каждого поля — ими проверяется
# запись на диск.
_MUTATIONS = {
    "workingFolder": "D:/TTRPG/Sessions",
    "mergerMaxGap": "2.5",
    "mergerOocMode": "italic",
    "interfaceLanguage": "en",
    "showTooltips": False,
    "soundOnDone": False,
    "asrDevice": "cpu",
    "asrComputeType": "int8",
    "asrBeamSize": "8",
    "asrLanguage": "en",
    "gigaamVariant": "e2e_rnnt",
    "gigaamPrecision": "int8",
    "asrNumThreads": "2",
    "chunkingEnabled": True,
    "chunkingChunkChars": "60000",
    "chunkingOverlapRatio": "0.35",
    "renderer": "combat-aware",
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(True, True), ("true", True), ("false", False), (0, False), ("1", True)],
)
def test_to_bool_reads_qsettings_spellings(raw, expected):
    """QSettings отдаёт булево строкой, и разбор — не тождество."""
    assert _to_bool(raw) is expected


@pytest.mark.parametrize(("field", "expected"), sorted(_DEFAULTS.items()))
def test_default_value(scratch_settings, field, expected):
    prefs = AppPreferences()
    assert getattr(prefs, field) == expected


def test_default_working_folder_points_at_sessions(scratch_settings):
    # Путь зависит от домашнего каталога, поэтому проверяется хвост, а
    # не полное совпадение.
    assert "Sessions" in AppPreferences().workingFolder


@pytest.mark.parametrize(("field", "value"), sorted(_MUTATIONS.items()))
def test_value_survives_restart(scratch_settings, field, value):
    """Второй экземпляр видит запись — значит она дошла до диска.

    Проверять на том же объекте бессмысленно: поле, которое только
    держит значение в памяти и ничего не пишет, прошло бы такую
    проверку.
    """
    prefs = AppPreferences()
    assert getattr(prefs, field) != value, (
        f"{field}: подставленное значение совпало с дефолтом — "
        "проверка перестала различать запись и её отсутствие"
    )
    setattr(prefs, field, value)

    assert getattr(AppPreferences(), field) == value


def test_renderer_survives_restart(scratch_settings):
    """Выбор рендерера переживает перезапуск, как и соседи.

    Проверка восстановлена из мёртвой функции ``_renderer_round_trip``,
    лежавшей за блоком ``__main__`` и не выполнявшейся никогда.
    """
    prefs = AppPreferences()
    assert prefs.renderer == "plain-text", "по умолчанию остаётся старый формат"

    prefs.renderer = "combat-aware"
    assert AppPreferences().renderer == "combat-aware"


def test_build_asr_options_coerces_strings(scratch_settings):
    """Настройки хранятся строками, а ``AsrOptions`` ждёт числа."""
    prefs = AppPreferences()
    prefs.asrDevice = "cpu"
    prefs.asrComputeType = "int8"
    prefs.asrBeamSize = "8"
    prefs.asrLanguage = "en"
    prefs.gigaamVariant = "e2e_rnnt"
    prefs.gigaamPrecision = "int8"
    prefs.asrNumThreads = "2"

    opts = AppPreferences().build_asr_options()

    assert opts.device == "cpu"
    assert opts.compute_type == "int8"
    assert opts.language == "en"
    assert opts.gigaam_variant == "e2e_rnnt"
    assert opts.gigaam_precision == "int8"
    # Числа: тип проверяется отдельно от значения — строка "8" равна 8
    # не была бы, но `int` с `str` сравнивать и не надо, а вот
    # `beam_size == "8"` прошло бы, будь коэрция забыта.
    assert opts.beam_size == 8 and isinstance(opts.beam_size, int)
    assert opts.num_threads == 2 and isinstance(opts.num_threads, int)


def test_build_chunking_options_coerces_strings(scratch_settings):
    prefs = AppPreferences()
    prefs.chunkingEnabled = True
    prefs.chunkingChunkChars = "60000"
    prefs.chunkingOverlapRatio = "0.35"

    copts = AppPreferences().build_chunking_options()

    assert copts.enabled is True
    assert copts.chunk_chars == 60_000 and isinstance(copts.chunk_chars, int)
    assert isinstance(copts.overlap_ratio, float)
    assert abs(copts.overlap_ratio - 0.35) < 1e-9
