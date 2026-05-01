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
передаётся вручную, либо определяется по слоёному fallback'у:

    1) ``craig-start`` маркер в чате (точный якорь);
    2) системная таймзона машины, где идёт мердж;
    3) эвристика min|delta| по первому сообщению.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from domain.annotations import ChatMessage
from sources.base import Source

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

    def extract(self, session_dir: Path) -> list[ChatMessage]:
        """Прочитать chat log и вернуть ``list[ChatMessage]``.

        Таймштампы — в секундах от начала записи (Craig ``info.txt``).
        """
        entries = parse_fvtt_log(self.chat_log_path)
        if not entries:
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

        tz_offset = self.tz_offset
        if tz_offset is None:
            # Step 1: явный якорь в чате — самое надёжное.
            tz_offset = find_anchor_offset(entries, rec_start)
        if tz_offset is None:
            # Step 2: системная таймзона. Работает, пока чат экспортит и
            # мердж запускает один и тот же человек на одной машине.
            tz_offset = _system_utc_offset_hours()
        if tz_offset is None:
            # Step 3: fallback-эвристика. Промахнётся, если Craig запустили
            # сильно позже начала FVTT-болтовни — но лучше, чем ничего.
            tz_offset = guess_tz_offset(entries, rec_start)

        messages: list[ChatMessage] = []
        for entry in entries:
            entry_utc = entry["datetime"] - timedelta(hours=tz_offset)
            entry_utc = entry_utc.replace(tzinfo=timezone.utc)
            at = (entry_utc - rec_start).total_seconds()
            if at < 0:
                # Сообщение отправлено до старта записи — отбрасываем
                continue
            messages.append(_to_chat_message(entry, at))

        return messages


def _to_chat_message(entry: dict, at: float) -> ChatMessage:
    """Сконвертировать raw-entry ``parse_fvtt_log`` в ``ChatMessage``."""
    return ChatMessage(
        at=at,
        channel=_DEFAULT_CHANNEL,
        author=entry["speaker"],
        text=entry["text"],
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
    """Port ``guess_tz_offset``: перебирает UTC offset -12..+14 и выбирает лучший.

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


def _system_utc_offset_hours() -> float | None:
    """UTC offset машины, где идёт мердж, в часах.

    Использует ``datetime.now().astimezone().utcoffset()`` — корректно
    учитывает DST на текущую дату. Возвращает ``None`` только если
    таймзона недоступна (на нормальных Linux/Win/macOS такого не бывает).
    """
    try:
        offset = datetime.now().astimezone().utcoffset()
    except Exception:
        return None
    if offset is None:
        return None
    return offset.total_seconds() / 3600
