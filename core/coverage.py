"""Что из игровых логов осталось без аудио.

Отвечает на один вопрос: запись Craig покрывает сессию целиком — или
её включили позже, и часть чата с боями осталась без звука?

Мерджер и так выбрасывает всё, что раньше старта записи (``at < 0``) —
иначе события уехали бы в отрицательное время. Проблема не в том, что
он выбрасывает, а в том, что раньше он делал это молча: человек
получал ``merged.txt`` без первого часа игры и без боёвки и узнавал об
этом сильно позже. Здесь считается то же самое, но заранее и с
человеческой формулировкой — чтобы UI показал это до запуска.

Модуль читает те же файлы и теми же средствами, что и pipeline
(``info.txt``, чат-лог, ``Бой*.txt``), и не запускает ни ASR, ни мердж —
экран сессии зовёт его синхронно на открытии папки. Совпадение с
мерджером здесь принципиально: баннер, который считает не те сообщения,
что реально попадут в ``merged.txt``, хуже отсутствующего баннера.

Все функции возвращают ``None`` на любой ошибке, а не бросают: папка
сессии на диске у пользователя регулярно неполная, и экран должен
рисоваться в любом случае.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.discovery import find_fvtt_chat_log
from core.file_matchers import detect_combat_logs, detect_craig_segments
from core.timeline_window import parse_combat_file, parse_info_start
from sources.game_log.fvtt_chat import parse_fvtt_log, resolve_tz_offset

#: Насколько поздний старт записи считаем достойным упоминания. Две
#: минуты — это ещё «нажал Record, потом открыл Foundry», нормальный
#: порядок действий, а не потеря материала.
_MIN_REPORTABLE_GAP_SECONDS = 120.0


@dataclass(frozen=True)
class _ChatFacts:
    """Промежуточный результат разбора чат-лога."""

    total: int = 0
    dropped: int = 0
    first_entry_utc: datetime | None = None
    #: Разрешённый UTC-офсет лога. ``None`` — чат-лога нет или он не
    #: разобрался; тогда время боёв печатать не в чем, кроме зоны ОС.
    tz_offset: float | None = None


@dataclass(frozen=True)
class CoverageReport:
    """Сколько игровых событий осталось за пределами записи."""

    #: На сколько секунд старт записи позже первого сообщения в чате.
    #: Ноль или отрицательное — запись началась вовремя.
    late_start_seconds: float
    #: Всего записей в чат-логе и сколько из них раньше старта записи.
    chat_total: int
    chat_dropped: int
    #: Бои, целиком уместившиеся до старта записи, — то есть без звука.
    #: Формат элемента: ``("Бой", "19:11", "20:18")``.
    combats_missed: tuple[tuple[str, str, str], ...]

    @property
    def is_empty(self) -> bool:
        """``True``, когда рассказывать не о чем.

        Про ``chat_dropped`` здесь намеренно не спрашиваем: он больше
        нуля при любом, даже секундном опоздании записи, а «привет
        всем» за десять секунд до Record — это норма, а не потеря.
        Порог решает, стоит ли вообще открывать рот; пропущенный бой
        стоит всегда, каким бы маленьким ни был разрыв.
        """
        return (
            self.late_start_seconds < _MIN_REPORTABLE_GAP_SECONDS
            and not self.combats_missed
        )

    @property
    def message(self) -> str:
        """Человеческая формулировка для баннера. ``""`` если нечего сказать."""
        if self.is_empty:
            return ""

        parts: list[str] = []
        if self.late_start_seconds >= _MIN_REPORTABLE_GAP_SECONDS:
            parts.append(
                f"Запись началась на {_ru_duration(self.late_start_seconds)} "
                "позже начала чат-лога."
            )

        lost: list[str] = []
        if self.chat_dropped:
            # «сообщений» здесь не требует согласования по числу: в
            # конструкции «N из M сообщений» существительное управляется
            # частью «из M» и всегда стоит в родительном множественного —
            # «1 из 353 сообщений» так же верно, как «260 из 353».
            lost.append(f"{self.chat_dropped} из {self.chat_total} сообщений")
        for label, start, end in self.combats_missed:
            lost.append(f"{label} {start}–{end}")
        if lost:
            parts.append(f"Без аудио: {', '.join(lost)}.")

        return " ".join(parts)


def analyse_coverage(session_dir: Path) -> CoverageReport | None:
    """Посчитать покрытие сессии записью. ``None``, если считать не по чему.

    ``None`` означает «нет данных»: нет ``info.txt`` (не от чего
    отсчитывать) либо не удалось прочитать ни чат-лог, ни один бой. Это
    не то же самое, что «всё в порядке» — на такой ответ есть
    :attr:`CoverageReport.is_empty`. Смешивать их нельзя: иначе сессия,
    где всё хорошо, и сессия, которую не удалось прочитать, выглядят
    для вызывающего одинаково.
    """
    info_start = _session_start(session_dir)
    if info_start is None:
        return None

    chat = _analyse_chat(session_dir, info_start)
    combats_missed, combats_read = _analyse_combats(
        session_dir, info_start, chat.tz_offset
    )

    if chat.first_entry_utc is None and combats_read == 0:
        return None

    late = 0.0
    if chat.first_entry_utc is not None:
        late = (info_start - chat.first_entry_utc).total_seconds()

    return CoverageReport(
        late_start_seconds=late,
        chat_total=chat.total,
        chat_dropped=chat.dropped,
        combats_missed=combats_missed,
    )


def _session_start(session_dir: Path) -> datetime | None:
    """Старт записи Craig в UTC, или ``None``.

    Сперва ``info.txt`` в корне сессии, затем — первый Craig-сегмент.
    В сессиях, где запись перезапускали, ``info.txt`` лежит внутри
    ``craig-1/`` и подобных, а это как раз конфигурация, где поздний
    старт наиболее вероятен: терять её было бы обидно.
    """
    root = parse_info_start(session_dir / "info.txt")
    if root is not None:
        return root

    for segment in detect_craig_segments(session_dir):
        if segment.info_path is None:
            continue
        start = parse_info_start(segment.info_path)
        if start is not None:
            return start
    return None


def _analyse_chat(session_dir: Path, info_start: datetime) -> _ChatFacts:
    """Разобрать чат-лог: сколько всего, сколько до записи, какой офсет.

    Файл ищется тем же ``find_fvtt_chat_log``, что и в
    :mod:`core.pipeline` — не ``detect_fvtt_chat_logs``. Две функции
    поиска расходятся в шаблоне (``fvtt-log-*.txt`` против
    ``fvtt-log*.txt``), и взять здесь вторую значило бы посчитать файл,
    который мерджер потом не откроет.
    """
    chat_path = find_fvtt_chat_log(session_dir)
    if chat_path is None:
        return _ChatFacts()

    try:
        entries = parse_fvtt_log(chat_path)
    except (OSError, UnicodeError, ValueError):
        return _ChatFacts()
    if not entries:
        return _ChatFacts()

    try:
        offset = resolve_tz_offset(
            entries, info_start, combat_paths=detect_combat_logs(session_dir)
        ).offset_hours
    except (TypeError, ValueError):
        return _ChatFacts()

    times = [
        (e["datetime"] - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
        for e in entries
    ]
    return _ChatFacts(
        total=len(entries),
        dropped=sum(1 for t in times if t < info_start),
        first_entry_utc=min(times),
        tz_offset=offset,
    )


def _analyse_combats(
    session_dir: Path, info_start: datetime, tz_offset: float | None
) -> tuple[tuple[tuple[str, str, str], ...], int]:
    """``(бои без аудио, сколько боёв удалось прочитать)``.

    Бой, который старта записи застал (начался раньше, кончился позже),
    в пропущенные не попадает: часть его звука есть, и «без аудио» про
    него было бы неправдой.

    Счётчик прочитанных нужен вызывающему, чтобы отличить «боёв нет» от
    «бои есть, но не читаются»: во втором случае утверждать, что всё в
    порядке, мы не вправе.
    """
    missed: list[tuple[str, str, str]] = []
    read = 0
    for path in detect_combat_logs(session_dir):
        meta = parse_combat_file(path)
        if meta is None:
            continue
        read += 1
        if meta.ended_at >= info_start:
            continue
        missed.append((
            meta.label,
            _hhmm(meta.started_at, tz_offset, info_start),
            _hhmm(meta.ended_at, tz_offset, info_start),
        ))
    return tuple(missed), read


def _hhmm(
    moment: datetime, tz_offset: float | None, reference: datetime
) -> str:
    """UTC-момент → ``"19:11"`` в той же зоне, в которой считался чат.

    Офсет берётся разрешённый (``resolve_tz_offset``), а не зона машины:
    сессию могли писать в +2, а открыть папку на ноутбуке в UTC — и
    тогда время боя в баннере разошлось бы с временем в чат-логе,
    который пользователь видит рядом.

    Зоны ОС касаемся только когда чат-лога нет и офсет взять неоткуда;
    тогда — на дату сессии, а не на сегодня, иначе зимнюю сессию,
    открытую летом, унесёт на час.
    """
    if tz_offset is not None:
        return (moment + timedelta(hours=tz_offset)).strftime("%H:%M")
    try:
        return moment.astimezone(reference.astimezone().tzinfo).strftime("%H:%M")
    except (ValueError, OSError):
        return moment.strftime("%H:%M")


def _ru_duration(seconds: float) -> str:
    """``6420.0`` → ``"1 ч 47 мин"``.

    Парная функция для логов — ``sources.game_log.fvtt_chat._format_duration``
    (``"1h47m"``). Дублирование намеренное: аудитории разные, а
    ``sources`` по слоевым правилам не может импортировать ``core``.
    """
    total_minutes = int(round(abs(seconds) / 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours} ч {minutes} мин"
    if hours:
        return f"{hours} ч"
    return f"{minutes} мин"


__all__ = ["CoverageReport", "analyse_coverage"]
