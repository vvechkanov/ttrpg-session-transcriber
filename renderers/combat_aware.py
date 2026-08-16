"""CombatAwareRenderer — транскрипт, в котором бой виден как бой.

Вне боя формат не отличается от ``plain-text``: те же строки, тот же
порядок. Отличие начинается на ``encounter_start`` и заканчивается на
``encounter_end`` — участок между ними собирается в блок с шапкой,
инициативой, разметкой по раундам и ходам и итогом.

Зачем: транскрипт — сырьё для LLM, и в бою плоский список «реплика,
реплика, бросок» теряет ровно то, что делает бой боем — чей сейчас ход
и в каком раунде это происходит. Модель потом восстанавливает это
догадками, то есть выдумывает.

Блок собирается в буфер, а не пишется на лету: шапка содержит время
окончания, которое становится известно только на ``encounter_end``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from domain.events import ChatEvent, GameEvent, ScriptEvent, SpeechEvent

from renderers.base import Renderer
from renderers.plain_text import PlainTextRenderer

#: Имя сцены, которое ничего не значит. Foundry подставляет его сам,
#: когда бой не привязан к именованной сцене, — печатать это в шапке
#: хуже, чем не печатать ничего.
_EMPTY_SCENE_NAMES = frozenset({"", "unknown scene", "unnamed scene"})

_RULE = "━━━"
_INDENT = "  "

#: Игровые события, которые внутри блока идут отдельной строкой, а не
#: сворачиваются в заголовок хода.
#: Итоги приходят после ``encounter_end`` с тем же таймштампом, так
#: что блок нельзя закрывать сразу на конце боя — иначе подвал теряет
#: раунды и XP, а построчная статистика вываливается наружу.
_SUMMARY_ACTIONS = frozenset({
    "encounter_summary_global",
    "encounter_summary_actor",
})

_DETAIL_ACTIONS = frozenset({
    "action",
    "hp_change",
    "effect_applied",
    "effect_removed",
    "effect_changed",
    "movement",
})


class CombatAwareRenderer(Renderer):
    """Plain UTF-8 text, но бои размечены структурой."""

    def render(self, events: list[ScriptEvent]) -> bytes:
        plain = PlainTextRenderer()
        chunks: list[str] = []
        outside: list[ScriptEvent] = []
        block: _Block | None = None
        fought = 0

        def flush_outside() -> None:
            if outside:
                chunks.append(plain.render(outside).decode("utf-8"))
                outside.clear()

        for event in events:
            action = event.action if isinstance(event, GameEvent) else None

            if action == "encounter_start":
                # A block stays open past encounter_end while it waits
                # for the summaries, so the next fight starting is one
                # of the ways the previous one closes. Overwriting it
                # here dropped the whole first fight from the output.
                if block is not None:
                    chunks.append(block.render())
                    block = None
                flush_outside()
                fought += 1
                block = _Block(number=fought, scene=event.detail, start=event)
                continue

            if block is None:
                outside.append(event)
                continue

            if action == "encounter_end":
                block.end = event
                continue

            if block.has_ended and action not in _SUMMARY_ACTIONS:
                chunks.append(block.render())
                block = None
                outside.append(event)
                continue

            block.items.append(event)

        # Дамп может оборваться без ``encounter_end`` — бой не доиграли,
        # запись кончилась раньше, файл обрезан. Блок всё равно надо
        # закрыть, иначе он просто исчезнет из вывода.
        if block is not None:
            chunks.append(block.render())
        flush_outside()

        return "".join(chunks).encode("utf-8")


@dataclass
class _Block:
    """Один бой, собираемый до того, как станет известен его конец."""

    number: int
    scene: str
    start: GameEvent
    items: list[ScriptEvent] = field(default_factory=list)
    end: GameEvent | None = None

    @property
    def has_ended(self) -> bool:
        return self.end is not None

    def render(self) -> str:
        lines = [self._header()]

        initiative = self._initiative_line()
        if initiative:
            lines.append(initiative)

        lines.extend(self._body())
        lines.extend(self._per_actor())
        lines.append(self._footer())
        return "\n".join(lines) + "\n\n"

    # ── Шапка и подвал ───────────────────────────────────────────────

    def _header(self) -> str:
        title = f"БОЙ {self.number}"
        scene = (self.scene or "").strip()
        if scene.casefold() not in _EMPTY_SCENE_NAMES:
            title = f"{title}: {scene}"

        span = _span(
            self.start.wall_clock, self.end.wall_clock if self.end else None
        )
        head = f"{_RULE} {title} {_RULE}"
        return f"{head}  {span}" if span else head

    def _footer(self) -> str:
        summary = next(
            (
                e.detail
                for e in self.items
                if isinstance(e, GameEvent)
                and e.action == "encounter_summary_global"
            ),
            "",
        )
        tail = _summarise(summary)
        return f"{_RULE} Конец боя{tail} {_RULE}"

    def _per_actor(self) -> list[str]:
        """Построчная статистика — под телом, перед подвалом.

        Дамп её уже отформатировал; задача рендерера — не потерять её
        наружу и не смешать с ходами.
        """
        rows = [
            f"{_INDENT}· {e.actor}: {e.detail}"
            for e in self.items
            if isinstance(e, GameEvent)
            and e.action == "encounter_summary_actor"
            and e.actor
        ]
        return ["", "Итоги по участникам:", *rows] if rows else []

    def _initiative_line(self) -> str:
        """``Инициатива: Киран (28) → Бель (26) → …``.

        Порядок берётся из значений, а не из порядка записей: дамп
        перечисляет участников как ему удобно, а читать это будут как
        очередь ходов.
        """
        rolled: list[tuple[int, str]] = []
        for event in self.items:
            if not isinstance(event, GameEvent) or event.action != "initiative":
                continue
            value = _first_int(event.detail, "init")
            if value is not None and event.actor:
                rolled.append((value, event.actor))
        if not rolled:
            return ""
        rolled.sort(key=lambda pair: (-pair[0], pair[1]))
        return "Инициатива: " + " → ".join(f"{n} ({v})" for v, n in rolled)

    # ── Тело ─────────────────────────────────────────────────────────

    def _body(self) -> list[str]:
        lines: list[str] = []
        round_no = ""

        for event in self.items:
            if isinstance(event, GameEvent):
                if event.action == "initiative":
                    continue  # уже в шапке
                if event.action in _SUMMARY_ACTIONS:
                    continue  # уже в подвале
                if event.action == "round_start":
                    round_no = event.detail.strip()
                    continue
                if event.action == "turn_start":
                    lines.append("")
                    lines.append(_turn_heading(round_no, event))
                    continue
                if event.action in _DETAIL_ACTIONS:
                    lines.append(f"{_INDENT}· {_detail_line(event)}")
                continue

            lines.append(f"{_INDENT}{_stamp(event)}{_said(event)}")

        return lines


# ── Форматирование кусочков ──────────────────────────────────────────


def _turn_heading(round_no: str, event: GameEvent) -> str:
    parts = []
    if round_no:
        parts.append(f"Раунд {round_no}")
    parts.append(f"ход {event.actor}" if event.actor else "ход")
    heading = " · ".join(parts)
    return f"{heading} ({event.detail})" if event.detail else heading


def _detail_line(event: GameEvent) -> str:
    actor = f"{event.actor}: " if event.actor else ""
    return f"{actor}{event.detail}".strip()


def _said(event: ScriptEvent) -> str:
    if isinstance(event, SpeechEvent):
        return f"{event.speaker}: {event.text}"
    if isinstance(event, ChatEvent):
        return f"[ЧАТ] {event.author}: {event.text}"
    return ""


def _stamp(event: ScriptEvent) -> str:
    """``"[20:15] "`` или пусто, если время сессии неизвестно."""
    moment = event.wall_clock
    return f"[{moment.strftime('%H:%M')}] " if moment is not None else ""


def _span(start: datetime | None, end: datetime | None) -> str:
    if start is None:
        return ""
    if end is None:
        return f"[{start.strftime('%H:%M')} – …]"
    return f"[{start.strftime('%H:%M')} – {end.strftime('%H:%M')}]"


def _first_int(detail: str, key: str) -> int | None:
    match = re.search(rf"\b{re.escape(key)}\s*=\s*(-?\d+)", detail)
    return int(match.group(1)) if match else None


def _summarise(detail: str) -> str:
    """``rounds=4 | xp=90 | …`` → ``" · 4 раунда · XP +90"``.

    Из дампа берутся только те два числа, что читатель действительно
    использует. Остальное (party_lvl, difficulty, avg_gm_turn) остаётся
    в подробных строках — в подвале это шум.
    """
    parts: list[str] = []
    rounds = _first_int(detail, "rounds")
    if rounds is not None:
        parts.append(f"{rounds} {_plural_rounds(rounds)}")
    xp = _first_int(detail, "xp")
    if xp:
        parts.append(f"XP +{xp}")
    return (" · " + " · ".join(parts)) if parts else ""


def _plural_rounds(count: int) -> str:
    tail_100 = abs(count) % 100
    tail = abs(count) % 10
    if 11 <= tail_100 <= 14:
        return "раундов"
    if tail == 1:
        return "раунд"
    if tail in (2, 3, 4):
        return "раунда"
    return "раундов"
