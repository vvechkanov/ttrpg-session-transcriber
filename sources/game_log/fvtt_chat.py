"""FvttChatSource — чат-лог из Foundry VTT как источник ChatMessage-ов.

Port логики из ``scripts/parse_fvtt_chat.py`` (``parse_fvtt_log``,
``parse_info_start_time``, ``guess_tz_offset``, ``chat_to_segments``).
Сделан именно как port, а не обёртка: legacy-скрипт будет удалён в задаче
2.10, а логика парсинга должна жить здесь, в sources/game_log/.

Формат chat log:
    [M/D/YYYY, H:MM:SS AM/PM] SpeakerName
    Message text (возможно многострочный)
    ---------------------------

``info.txt`` от Craig содержит ``Start time: <ISO8601>`` в UTC.
Временные метки чата — в local time браузера, поэтому offset либо
передаётся вручную, либо определяется по слоёному fallback'у.

Лесенка живёт в одном месте — :func:`resolve_tz_offset`. Это важно:
раньше её знал только мерджер, а UI и таймлайн звали ``guess_tz_offset``
напрямую и получали другой ответ на тех же файлах. Все, кому нужен
offset, обязаны идти через резолвер.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from domain.annotations import ChatMessage
from sources.base import Source

logger = logging.getLogger(__name__)

_TS_RE = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{4},\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M)\]\s*(.+)$"
)
_SEPARATOR = "---------------------------"

# Маркер «здесь Craig стартанул»: пользователь оставляет в FVTT chat
# сообщение, начинающееся с ``craig-start`` (или ``craig start`` /
# ``craig_start``), регистр игнорируется. Опционально — в скобках или со
# слэшем перед: ``[craig-start]`` / ``/craig-start``.
_ANCHOR_MARKER_RE = re.compile(r"^\s*[/\[]?\s*craig[-_ ]?start\b", re.IGNORECASE)

# Реальные UTC-офсеты в природе живут в [-12, +14]. Если маркер даёт
# что-то за пределами — это либо опечатка времени, либо маркер от
# другой записи, либо мусор. Игнорируем, не доверяем.
_MAX_REASONABLE_OFFSET_H = 14.0

# FVTT chat log не размечает ic/ooc: мы ставим "ic" по умолчанию, так как
# типичный use case — логирование ролевых сообщений. Если позже появится
# разбор chat flavor'ов и OOC-маркеров, канал можно будет вычислять.
_DEFAULT_CHANNEL = "ic"


#: Ступени лесенки :func:`resolve_tz_offset`, от надёжного к шаткому.
TzSource = Literal["explicit", "anchor", "system", "heuristic"]

#: Ступени, чей ответ не является догадкой. Белый список, а не «всё
#: кроме heuristic»: иначе любая новая ступень автоматически считалась
#: бы надёжной, и UI поставил бы зелёную галочку на угаданном офсете.
_RELIABLE_SOURCES: frozenset[str] = frozenset({"explicit", "anchor", "system"})


@dataclass(frozen=True)
class TzResolution:
    """Чем закончился поиск UTC-офсета для чат-лога.

    Возвращается :func:`resolve_tz_offset`. Помимо самого офсета несёт
    то, откуда он взялся — UI показывает это пользователю, а тесты по
    ``source`` проверяют, что сработала именно та ступень лесенки.
    """

    offset_hours: float
    #: Какая ступень дала ответ: ``explicit`` (передан руками),
    #: ``anchor`` (маркер ``craig-start`` в чате), ``system``
    #: (таймзона машины на дату записи), ``heuristic`` (min|delta| по
    #: первому сообщению — ненадёжна, см. :func:`guess_tz_offset`).
    source: TzSource

    @property
    def is_reliable(self) -> bool:
        """``False``, если офсет по сути угадан.

        Эвристика структурно ломается, когда запись начали заметно
        позже начала чата, — а это ровно тот случай, когда человеку
        и надо посмотреть на результат своими глазами.
        """
        return self.source in _RELIABLE_SOURCES


#: Ответ для пустого чат-лога. Офсет там ни на что не влияет — сдвигать
#: нечего, — но помечать его надёжным было бы враньём. Константа общая
#: с ``core.fvtt_helpers``, чтобы политика пустого лога жила в одном
#: месте, а не расползлась по слоям.
EMPTY_LOG_RESOLUTION = TzResolution(offset_hours=0.0, source="heuristic")


class FvttChatSource(Source):
    """Game log source — чат Foundry VTT."""

    name = "fvtt-chat"

    def __init__(
        self,
        chat_log_path: Path,
        info_file_path: Path | None = None,
        tz_offset: float | None = None,
    ) -> None:
        self.chat_log_path = chat_log_path
        self.info_file_path = info_file_path
        self.tz_offset = tz_offset
        #: Результат последнего :meth:`extract` — какой офсет взяли и
        #: откуда. ``None`` пока extract не вызывали. UI читает это,
        #: чтобы показать, чем разрешилась таймзона.
        self.last_resolution: TzResolution | None = None

    def extract(self, session_dir: Path) -> list[ChatMessage]:
        """Прочитать chat log и вернуть ``list[ChatMessage]``.

        Таймштампы — в секундах от начала записи (Craig ``info.txt``).
        """
        # Сбрасываем сразу: иначе при раннем возврате останется ответ от
        # предыдущего extract, и UI покажет офсет от чужого запуска.
        self.last_resolution = None

        entries = parse_fvtt_log(self.chat_log_path)
        if not entries:
            self.last_resolution = EMPTY_LOG_RESOLUTION
            return []

        info_path = self.info_file_path
        if info_path is None:
            # Автодетект: scripts/merge_whisperx.py ищет info.txt в session_dir.
            candidate = session_dir / "info.txt"
            if not candidate.exists():
                raise FileNotFoundError(
                    f"info.txt не найден в {session_dir}; "
                    "передайте info_file_path явно для выравнивания chat timestamps"
                )
            info_path = candidate

        rec_start = parse_info_start_time(info_path)

        resolution = resolve_tz_offset(entries, rec_start, explicit=self.tz_offset)
        self.last_resolution = resolution
        tz_offset = resolution.offset_hours

        messages: list[ChatMessage] = []
        earliest_at: float | None = None
        for entry in entries:
            entry_utc = entry["datetime"] - timedelta(hours=tz_offset)
            entry_utc = entry_utc.replace(tzinfo=timezone.utc)
            at = (entry_utc - rec_start).total_seconds()
            if earliest_at is None or at < earliest_at:
                earliest_at = at
            if at < 0:
                # Сообщение отправлено до старта записи — отбрасываем
                continue
            messages.append(_to_chat_message(entry, at))

        dropped = len(entries) - len(messages)
        if dropped:
            # Раньше это происходило молча. На сессии, где Craig
            # запустили с опозданием, так исчезали сотни сообщений и
            # целые бои — и замечали это в лучшем случае через месяц.
            logger.warning(
                "%s: %d of %d chat entries predate the recording and were "
                "dropped (recording starts %s after the log begins, "
                "tz offset %+.2fh from %s)",
                self.chat_log_path.name,
                dropped,
                len(entries),
                _format_duration(-earliest_at if earliest_at is not None else 0.0),
                tz_offset,
                resolution.source,
            )

        return messages


def _format_duration(seconds: float) -> str:
    """``6420.0`` → ``"1h47m"``. Для логов.

    Парная функция для UI — ``core.coverage._ru_duration`` (``"1 ч 47 мин"``).
    Объединять их не надо: аудитории и языки разные, а ``sources`` по
    слоевым правилам не может импортировать ``core``.
    """
    total_minutes = int(round(abs(seconds) / 60))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m"


def _to_chat_message(entry: dict, at: float) -> ChatMessage:
    """Сконвертировать raw-entry ``parse_fvtt_log`` в ``ChatMessage``."""
    return ChatMessage(
        at=at,
        channel=_DEFAULT_CHANNEL,
        author=entry["speaker"],
        text=entry["text"],
    )


# ── Резолвер офсета ──────────────────────────────────────────────────────


def resolve_tz_offset(
    entries: list[dict],
    recording_start_utc: datetime,
    *,
    explicit: float | None = None,
) -> TzResolution:
    """Определить UTC offset чат-лога. Единственная точка правды.

    Лесенка, от самого надёжного к самому шаткому:

    1. ``explicit`` — офсет передали руками, вопросов нет;
    2. маркер ``craig-start`` в чате — точный якорь, см.
       :func:`find_anchor_offset`;
    3. системная таймзона машины — верно, пока чат экспортит и мердж
       запускает один человек на одной машине (обычный случай);
    4. :func:`guess_tz_offset` — угадайка, помечается как ненадёжная.

    Пустой ``entries`` даёт :data:`EMPTY_LOG_RESOLUTION`.

    ``recording_start_utc`` нормализуется здесь и только здесь: наивный
    считается UTC (Craig всегда пишет UTC), aware приводится к UTC.
    Ниже по течению ``find_anchor_offset`` делает ``replace(tzinfo=None)``
    и молча предполагает UTC — без нормализации ``info.txt`` с
    ``+02:00`` вместо ``Z`` развёл бы потребителей на те же два часа,
    от которых мы уходим.
    """
    if explicit is not None:
        return TzResolution(offset_hours=float(explicit), source="explicit")

    if not entries:
        return EMPTY_LOG_RESOLUTION

    if recording_start_utc.tzinfo is None:
        recording_start_utc = recording_start_utc.replace(tzinfo=timezone.utc)
    else:
        recording_start_utc = recording_start_utc.astimezone(timezone.utc)

    anchored = find_anchor_offset(entries, recording_start_utc)
    if anchored is not None:
        return TzResolution(offset_hours=anchored, source="anchor")

    system = _system_utc_offset_hours(recording_start_utc)
    if system is not None:
        return TzResolution(offset_hours=system, source="system")

    return TzResolution(
        offset_hours=guess_tz_offset(entries, recording_start_utc),
        source="heuristic",
    )


# ── Port функций из scripts/parse_fvtt_chat.py ───────────────────────────


def parse_fvtt_log(path: Path) -> list[dict]:
    """Port ``parse_fvtt_log``: читает fvtt-log-*.txt в список entry-dict-ов.

    Формат entry: ``{"datetime": datetime (naive, local), "speaker": str, "text": str}``.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = text.split(_SEPARATOR)

    entries: list[dict] = []
    for block in blocks:
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue

        m = _TS_RE.match(lines[0].strip())
        if not m:
            continue

        ts_str, speaker = m.group(1), m.group(2).strip()
        try:
            dt = datetime.strptime(ts_str, "%m/%d/%Y, %I:%M:%S %p")
        except ValueError:
            continue

        body = "\n".join(ln.strip() for ln in lines[1:]).strip()
        # Тривиальные сообщения ("+", пустота) отбрасываем — port из legacy.
        if not body or body in ("+",):
            continue

        entries.append({"datetime": dt, "speaker": speaker, "text": body})

    return entries


def parse_info_start_time(path: Path) -> datetime:
    """Port ``parse_info_start_time``: извлекает ``Start time:`` из Craig info.txt."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("start time:"):
            raw = stripped.split(":", 1)[1].strip()
            raw = raw.replace("Z", "+00:00")
            return datetime.fromisoformat(raw)
    raise ValueError(f"'Start time:' not found in {path}")


def guess_tz_offset(entries: list[dict], recording_start_utc: datetime) -> float:
    """Последняя ступень лесенки: перебор UTC offset -12..+14, лучший выигрывает.

    Не зовите напрямую — идите через :func:`resolve_tz_offset`, иначе
    получите ответ, отличный от того, что взял мерджер.

    Метод структурно ненадёжен: он предполагает, что Record в Craig
    нажали примерно тогда же, когда началась переписка в Foundry. Если
    запись начали заметно позже, промах равен целому UTC-офсету —
    см. ``tests/fixtures/tz_late_start`` (реальная сессия, запись на
    1 ч 47 мин позже начала чата, эвристика даёт 0 вместо +2).

    "Лучший" — тот, при котором первый chat entry оказывается ближе всего
    (по абсолютной величине) к recording_start. Знак delta не важен:
    первое сообщение в FVTT chat часто отправлено ДО нажатия Record в Craig
    (расстановка фишек, броски инициативы, общий чат до игры) — отбрасывание
    отрицательных delta приводит к выбору неверного offset, сдвинутого на час
    относительно реального.
    """
    if not entries:
        return 0.0

    first_local = entries[0]["datetime"]
    best_offset = 0.0
    best_delta = float("inf")

    for offset_h in range(-12, 15):
        entry_utc = first_local - timedelta(hours=offset_h)
        entry_utc = entry_utc.replace(tzinfo=timezone.utc)
        delta = abs((entry_utc - recording_start_utc).total_seconds())
        if delta < best_delta:
            best_delta = delta
            best_offset = float(offset_h)

    return best_offset


def find_anchor_offset(
    entries: list[dict], recording_start_utc: datetime
) -> float | None:
    """Найти ``craig-start`` маркер и вычислить точный UTC offset.

    Маркер — любое сообщение, чей текст начинается с ``craig-start`` (или
    ``craig start`` / ``craig_start``), регистр не важен; опциональны
    скобки/слэш перед — ``[craig-start]``, ``/craig-start``.

    Идея: пользователь оставляет такое сообщение в FVTT chat в момент
    нажатия Record в Craig. Local timestamp этого сообщения соответствует
    UTC ``Start time`` из ``info.txt`` — точное соответствие, никаких
    эвристик.

    Возвращает offset в часах (округлённый до ближайшего целого, чтобы
    погасить секундный jitter между «нажал Record» и «отправил маркер»).
    Возвращает ``None`` если маркер не найден или вычисленный offset
    выходит за разумные пределы (±14 часов).
    """
    rec_naive = recording_start_utc.replace(tzinfo=None)
    for entry in entries:
        if not _ANCHOR_MARKER_RE.match(entry["text"]):
            continue
        delta_seconds = (entry["datetime"] - rec_naive).total_seconds()
        offset_h = float(round(delta_seconds / 3600))
        if abs(offset_h) > _MAX_REASONABLE_OFFSET_H:
            # Маркер сломан / не от этой записи / опечатка — игнорируем.
            return None
        return offset_h
    return None


def _system_utc_offset_hours(at: datetime) -> float | None:
    """UTC offset машины, где идёт мердж, **на момент записи сессии**.

    ``at`` — время старта записи (aware). Офсет спрашивается именно на
    эту дату, а не на «сейчас»: иначе январскую сессию, смердженную в
    августе, унесёт на час — ``datetime.now()`` в Праге вернёт +2, тогда
    как в момент игры было +1. Промах тихий, потому что ступень
    ``system`` считается надёжной и никто не подсвечивает результат.

    Возвращает ``None`` только если таймзона недоступна (на нормальных
    Linux/Win/macOS такого не бывает).
    """
    try:
        offset = at.astimezone().utcoffset()
    except Exception:
        return None
    if offset is None:
        return None
    return offset.total_seconds() / 3600
