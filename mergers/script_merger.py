"""ScriptMerger: Timeline → sorted list[ScriptEvent] with same-speaker gluing."""

from domain.annotations import SpeechSegment
from domain.events import ChatEvent, ScriptEvent, SpeechEvent
from domain.timeline import Timeline

from mergers.base import Merger


def _event_sort_key(e: ScriptEvent) -> tuple[float, int]:
    if isinstance(e, SpeechEvent):
        return (e.start, 0)
    if isinstance(e, ChatEvent):
        return (e.at, 1)
    return (e.at, 2)  # GameEvent — reserved


class ScriptMerger(Merger):
    def __init__(self, gap_sec: float = 1.0):
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

        # Step 5: game log
        # P2: game_log → GameEvent not yet implemented

        # Step 6: interleave and sort
        events: list[ScriptEvent] = [*speech_events, *chat_events]
        events.sort(key=_event_sort_key)

        # Step 7
        return events
