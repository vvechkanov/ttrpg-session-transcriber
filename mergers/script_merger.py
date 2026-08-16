"""ScriptMerger: Timeline → sorted list[ScriptEvent] with same-speaker gluing."""

from datetime import datetime, timedelta

from domain.annotations import SpeechSegment
from domain.events import ChatEvent, GameEvent, ScriptEvent, SpeechEvent
from domain.timeline import Timeline

from mergers.base import Merger


def _stamp_wall_clock(
    events: list[ScriptEvent], recording_start: datetime | None
) -> None:
    """Проставить событиям абсолютное время, если оно известно.

    Мерджер — единственное место, где встречаются относительные ``at``
    и старт записи, поэтому штамп ставится здесь, а не в рендерере: так
    контракт ``render(events) -> bytes`` остаётся нетронутым, а время
    достаётся любому будущему рендереру даром.

    ``recording_start`` уже в зоне сессии (см. :class:`Timeline`), и
    арифметика над aware-datetime зону сохраняет — значит форматировать
    можно прямо, без дополнительных знаний о таймзонах.
    """
    if recording_start is None:
        return
    for event in events:
        offset = event.start if isinstance(event, SpeechEvent) else event.at
        event.wall_clock = recording_start + timedelta(seconds=offset)


def _event_sort_key(e: ScriptEvent) -> tuple[float, int]:
    if isinstance(e, SpeechEvent):
        return (e.start, 0)
    if isinstance(e, ChatEvent):
        return (e.at, 1)
    return (e.at, 2)  # GameEvent


#: Silence, in seconds, that still counts as "the same turn".
#:
#: Was 1.0, inherited from the WhisperX-era merge_whisperx.py. That
#: value is tied to how Whisper chunks audio: it does not trim silence,
#: so consecutive segments from one speaker sit essentially back to
#: back — measured on a real session, median gap 0.06 s, and 87% of
#: same-speaker pairs under 1.0 s. Gluing at 1.0 s therefore rebuilt
#: whole turns.
#:
#: VAD-sliced backends (GigaAM) behave the opposite way: the VAD cuts
#: silence out, so the gap between segments is the *actual pause* in
#: speech — median 1.41 s on the same session, only 26% under 1.0 s.
#: At the old threshold a two-minute monologue stayed shattered into
#: five or six separate turns, and the share of text sitting in runs
#: of five-plus consecutive same-speaker turns went from 4.1% (old
#: pipeline) to 16.6%.
#:
#: Swept against the old pipeline's conversational structure on
#: session 15 (2273 turns, mean run 1.24, max 11, 4.1% in long runs):
#:
#:     gap    turns   mean run   max   % in runs >=5
#:     1.0     2749       1.58    18           16.6
#:     1.5     2374       1.36     9            7.9
#:     2.0     2150       1.23     8            3.9   <- matches
#:     3.0     1962       1.12     6            1.1
#:
#: 2.0 reproduces the old structure almost exactly. Higher values keep
#: "improving" the numbers, but only by gluing across genuine turn
#: boundaries — that hides interleaving rather than fixing it.
#:
#: The Whisper path is barely affected: raising 1.0 -> 2.0 there glues
#: 160 more pairs out of 2411, because its gaps are near zero anyway.
DEFAULT_MERGE_GAP_SEC = 2.0


class ScriptMerger(Merger):
    def __init__(self, gap_sec: float = DEFAULT_MERGE_GAP_SEC):
        self.gap_sec = gap_sec

    def merge(self, timeline: Timeline) -> list[ScriptEvent]:
        # Step 1: speech gluing (same-speaker, small-gap)
        sorted_speech = sorted(timeline.speech, key=lambda s: s.start)
        glued: list[SpeechSegment] = []
        for seg in sorted_speech:
            if glued:
                prev = glued[-1]
                if (
                    seg.speaker is not None
                    and prev.speaker is not None
                    and seg.speaker == prev.speaker
                    and seg.start - prev.end <= self.gap_sec
                ):
                    glued[-1] = SpeechSegment(
                        start=prev.start,
                        end=max(prev.end, seg.end),
                        speaker=prev.speaker,
                        text=(prev.text.rstrip() + " " + seg.text.lstrip()).strip(),
                        confidence=None,
                    )
                    continue
            glued.append(seg)

        # Step 2: speech → SpeechEvent
        speech_events: list[ScriptEvent] = [
            SpeechEvent(
                start=seg.start,
                end=seg.end,
                speaker=seg.speaker or "",
                text=seg.text,
                emotion=None,
                parallel_group=None,
            )
            for seg in glued
        ]

        # Step 3: chat → ChatEvent
        chat_events: list[ScriptEvent] = []
        for msg in timeline.chat:
            channel: str = msg.channel if msg.channel in ("ic", "ooc") else "ic"
            chat_events.append(
                ChatEvent(
                    at=msg.at,
                    channel=channel,  # type: ignore[arg-type]
                    author=msg.author,
                    text=msg.text,
                )
            )

        # Step 4: emotions
        # P2: emotion projection not yet implemented

        # Step 5: game log → GameEvent
        game_events: list[ScriptEvent] = [
            GameEvent(
                at=entry.at,
                actor=entry.actor,
                action=entry.action,
                detail=entry.detail,
            )
            for entry in timeline.game_log
        ]

        # Step 6: interleave and sort
        events: list[ScriptEvent] = [*speech_events, *chat_events, *game_events]
        events.sort(key=_event_sort_key)

        # Step 7: stamp wall-clock times, if the session knows them.
        _stamp_wall_clock(events, timeline.recording_start)

        # Step 8
        return events
