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

Изоляция строже, чем в скрипте: тот уводил ``QSettings`` в общий
``TempLocation`` и звал ``.clear()`` — то есть чистил тот же INI, в
который смотрит ``tests/ui_qml_smoke/test_settings_screen_promises.py``
(единственный такой сосед). Здесь каждый тест получает собственный
``tmp_path``.

ЧЕГО ЗДЕСЬ НЕТ И НЕ МОЖЕТ БЫТЬ — восстановления исходного пути.
``QSettings`` не даёт его прочитать, сохранять нечего, поэтому
``finally`` уводит процесс в общий ``TempLocation``, а не «возвращает
на место». Это осознанный побочный эффект, а не изоляция: после этого
файла процесс смотрит в temp, а не в настоящий каталог настроек. Тот
же эффект уже создаёт названный выше сосед, и он его не снимает вовсе;
здесь важно, что в temp, а не в домашний каталог разработчика, — иначе
сломанная запись портила бы его настоящие настройки.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Как и у соседей по каталогу: core.pipeline импортируется до ui.*,
# чтобы не поймать циклический импорт через sources/__init__.
from core.pipeline import run as _warm  # noqa: F401,E402

from PySide6.QtCore import Property, QSettings, QStandardPaths  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from ui.models.app_preferences import AppPreferences, _to_bool  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QGuiApplication:
    """Держит ссылку на приложение весь модуль.

    Именно ссылку: без неё единственный Python-владелец
    ``QGuiApplication`` умирает вместе с кадром функции, если приложение
    создано здесь (запуск одного этого файла). Соседи по каталогу держат
    её либо module-scoped фикстурой, либо списком ``_ALIVE``.
    """
    inst = QGuiApplication.instance()
    if inst is not None:
        return inst
    created = QGuiApplication(sys.argv or [""])
    created.setApplicationName("Session Transcriber")
    created.setOrganizationName("Session Transcriber")
    return created


@pytest.fixture()
def scratch_settings(app: QGuiApplication, tmp_path: Path):
    """Увести INI ``AppPreferences`` в отдельный каталог на один тест.

    ``AppPreferences`` открывает хранилище, называя организацию и
    приложение явно, поэтому имена на ``QGuiApplication`` его никуда не
    уводят — подменять надо путь формата.
    """
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    try:
        yield tmp_path
    finally:
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
    """Дефолт — именно ``~/Sessions``, а не что-то, где есть это слово.

    Проверка по вхождению («Sessions» in путь) зеленела бы и для
    ``~/Sessions-old``, и для ``~/ArchivedSessions``, и для чего угодно
    с таким родительским каталогом. Контракт же
    ``_default_working_folder`` конкретен: ``Path.home() / "Sessions"``,
    — так и сравнивается. Сравнение идёт через ``Path``, чтобы не
    зависеть от разделителя платформы.
    """
    assert Path(AppPreferences().workingFolder) == Path.home() / "Sessions"


def _declared_properties() -> set[str]:
    """Имена ``QtCore.Property`` на классе.

    Именно QtCore.Property, а не встроенный ``property``: свойства QML
    объявлены декоратором Qt и питоновскому ``property`` не родня.
    """
    return {
        name
        for name in dir(AppPreferences)
        if not name.startswith("_")
        and isinstance(getattr(AppPreferences, name, None), Property)
    }


def test_every_property_has_a_default_check(scratch_settings):
    """Дефолт каждого свойства проверяется — список сверяется с классом.

    Без этого «список держится полным» — честное слово: новое
    ``@Property`` никто бы не заметил, и ни одна проверка не покраснела
    бы. Ровно тот класс, против которого написан весь этот дифф.

    ``_DEFAULTS`` и ``_MUTATIONS`` сверяются РАЗДЕЛЬНО, двумя тестами, и
    это не педантизм. Проверка по их объединению зеленела, когда поле
    пропадало из одной половины: замерено — убрать ``renderer`` только
    из ``_DEFAULTS``, и набор тихо теряет ``test_default_value``
    (44 теста становятся 43), а сторож полноты остаётся зелёным. То
    есть он не видел ровно того дрейфа, ради которого заведён.

    ``workingFolder`` исключён осознанно: его дефолт зависит от
    домашнего каталога, поэтому проверяется отдельным тестом по
    вхождению, а не равенством.
    """
    declared = _declared_properties()
    assert declared, "ни одного QtCore.Property не нашлось — сломана сама проверка"

    missing = sorted(declared - set(_DEFAULTS) - {"workingFolder"})
    assert not missing, (
        "у этих свойств AppPreferences не проверяется дефолт — добавь их "
        "в _DEFAULTS:\n  " + "\n  ".join(missing)
    )
    stale = sorted(set(_DEFAULTS) - declared)
    assert not stale, (
        "эти имена перечислены в _DEFAULTS, но свойствами AppPreferences "
        "не являются — список отстал от кода:\n  " + "\n  ".join(stale)
    )


def test_every_property_has_a_persistence_check(scratch_settings):
    """Запись каждого свойства проверяется — список сверяется с классом."""
    declared = _declared_properties()
    assert declared, "ни одного QtCore.Property не нашлось — сломана сама проверка"

    missing = sorted(declared - set(_MUTATIONS))
    assert not missing, (
        "у этих свойств AppPreferences не проверяется запись на диск — "
        "добавь их в _MUTATIONS:\n  " + "\n  ".join(missing)
    )
    stale = sorted(set(_MUTATIONS) - declared)
    assert not stale, (
        "эти имена перечислены в _MUTATIONS, но свойствами "
        "AppPreferences не являются — список отстал от кода:\n  "
        + "\n  ".join(stale)
    )


def _collision_probes() -> list[dict[str, object]]:
    """Два набора значений, вместе различающие ЛЮБУЮ пару полей.

    ``_MUTATIONS`` для этой пробы не годится, и внешнее ревью назвало
    почему: там несколько пар делят значение — ``interfaceLanguage`` и
    ``asrLanguage`` оба ``"en"``, ``asrComputeType`` и
    ``gigaamPrecision`` оба ``"int8"``, булевы поля тоже совпадают. Если
    склеятся ключи ВНУТРИ такой пары, оба поля всё равно прочитаются
    ожидаемыми, и проба останется зелёной ровно на том случае, ради
    которого написана.

    Строкам выдаётся уникальный маркер с именем поля — этого хватает за
    один проход. С булевыми так нельзя: значений всего два, а полей три,
    и в любом одном проходе какая-то пара неизбежно совпадёт. Поэтому
    проходов два, и каждому булевому полю достаётся СВОЯ пара значений
    по проходам: (False, True), (True, False), (True, True). Любые два
    поля различаются хотя бы в одном проходе, а склеенный ключ отдаёт
    значение последней записи — то есть в этом проходе и попадается.

    Значения намеренно не «правдоподобные»: проба проверяет адресацию
    хранилища, а не разбор значений, и правдоподобие тут маскировало бы
    совпадения.
    """
    bool_fields = [f for f, v in _MUTATIONS.items() if isinstance(v, bool)]
    # Различные битовые пары, по одной на булево поле.
    patterns = [(False, True), (True, False), (True, True), (False, False)]
    assert len(bool_fields) <= len(patterns), (
        "булевых полей стало больше, чем заготовлено различающих пар — "
        "добавь проход или пары, иначе проба перестанет различать их"
    )

    probes: list[dict[str, object]] = []
    for pass_index in (0, 1):
        probe: dict[str, object] = {}
        for field, value in _MUTATIONS.items():
            if isinstance(value, bool):
                probe[field] = patterns[bool_fields.index(field)][pass_index]
            else:
                probe[field] = f"probe{pass_index}-{field}"
        probes.append(probe)
    return probes


def test_all_fields_share_one_store_without_collisions(scratch_settings):
    """Все поля пишутся в ОДИН INI и читаются оттуда же.

    Тесты ниже параметризованы, и у каждого свой ``tmp_path``, то есть
    своё хранилище на одно поле. Это и есть их слепое пятно: опечатка в
    ключе, из-за которой два свойства пишут в одну строку INI, там не
    видна — в файле лежит ровно одно значение. Ключей у
    ``AppPreferences`` семнадцать, и они похожи друг на друга
    (``asr/beam_size``, ``asr/num_threads``, ``chunking/chunk_chars``),
    так что копипаста сеттера — правдоподобная мутация.
    """
    for pass_index, probe in enumerate(_collision_probes()):
        prefs = AppPreferences()
        for field, value in probe.items():
            setattr(prefs, field, value)

        restarted = AppPreferences()
        wrong = {
            field: (value, getattr(restarted, field))
            for field, value in probe.items()
            if getattr(restarted, field) != value
        }
        assert not wrong, (
            f"проход {pass_index}: после записи всех полей в одно "
            "хранилище часть читается не своей — похоже на коллизию "
            f"ключей QSettings: {wrong}"
        )


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
    # Тип проверяется отдельно от значения, и не ради строки: `== 8`
    # само по себе уже отсекает забытую коэрцию, потому что "8" != 8.
    # isinstance ловит другое — 8.0 и True, которые равенству
    # удовлетворяют, а в AsrOptions означают не то же самое.
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
