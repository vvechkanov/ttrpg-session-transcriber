"""Single-track ASR dispatch for the Qt shell.

Resolves a ``model_id`` (the string the TrackListModel rows carry —
``"gigaam"``, ``"faster-whisper"``, ``"whisper-lg"`` …) to a
configured speech :class:`sources.base.Source` instance, and provides
:func:`transcribe_one_track`, a thin pass-through that hands the
per-track hooks (progress + cancel) through to the source.

Model loading is amortised: :class:`ui.engines.asr_worker.AsrWorker`
calls :func:`make_source` once at the start of a batch and reuses the
returned instance for every track. A single 3 GB faster-whisper weight
file should not reload six times per session.

The module deliberately does **not** import PySide6 — core/ stays
toolkit-agnostic. The QML shell wraps it in a QThread; a future CLI
path could call this synchronously.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from domain.annotations import SpeechSegment
from sources.base import Source
from sources.speech.faster_whisper import FasterWhisperSource
from sources.speech.gigaam import GigaAMPrecision, GigaAMSource, GigaAMVariant


@dataclass(frozen=True)
class AsrOptions:
    """Per-backend knobs forwarded from UI preferences into ``make_source``."""

    device: str | None = None
    compute_type: str | None = None
    beam_size: int | None = None
    language: str | None = None
    gigaam_variant: str | None = None
    gigaam_precision: str | None = None
    num_threads: int | None = None


#: Alias re-exporting :class:`sources.base.Source` for UI callers.
#:
#: The UI layer cannot import from ``sources/`` directly (see
#: ``ARCHITECTURE.md §3`` — ``ui → core`` only). It needs a type to
#: annotate the opaque "configured ASR backend" handle that
#: :func:`make_source` hands out and that :class:`ui.engines.asr_worker
#: .AsrWorker` consumes; exposing the same class under a core name
#: keeps the dependency rule clean without introducing a parallel
#: protocol.
AsrSource = Source


#: Fraction 0..1 of this track's audio that has been processed so far.
TrackProgress = Callable[[float], None]

#: Polled between ASR chunks; returning ``True`` stops the loop and
#: returns whatever segments have been collected up to that point.
CancelProbe = Callable[[], bool]


def make_source(
    model_id: str,
    *,
    device: str = "cuda",
    language: str = "ru",
    speaker_map: dict[str, str] | None = None,
    options: AsrOptions | None = None,
) -> Source:
    """Resolve ``model_id`` → configured speech source.

    Accepted IDs mirror the ones :class:`ui.models.TrackListModel`
    stores in its ``ModelIdRole``, including the whisper-size aliases
    the override popover can pick:

        ``"gigaam"``                  → GigaAM RNNT FP32
        ``"faster-whisper"``          → faster-whisper large-v3-ru
        ``"whisper"``, ``"whisper-lg"``, ``"whisper-med"`` → same bundle,
            the size distinction is informational for the user; the
            shipped install is currently a single size.

    When ``options`` is provided, its non-``None`` fields override the
    positional ``device`` / ``language`` defaults and feed backend-specific
    knobs (compute_type, gigaam variant/precision, num_threads).

    Raises ``ValueError`` on unknown IDs so the worker surfaces the
    typo to the UI instead of silently falling back.
    """

    if options is None:
        options = AsrOptions()

    effective_device = options.device or device
    effective_language = options.language or language

    if model_id == "gigaam":
        variant = (
            GigaAMVariant(options.gigaam_variant)
            if options.gigaam_variant is not None
            else GigaAMVariant.RNNT
        )
        precision = (
            GigaAMPrecision(options.gigaam_precision)
            if options.gigaam_precision is not None
            else GigaAMPrecision.FP32
        )
        kwargs: dict[str, object] = dict(
            variant=variant,
            precision=precision,
            device=effective_device,
            speaker_map=speaker_map,
        )
        if options.num_threads is not None:
            kwargs["num_threads"] = options.num_threads
        return GigaAMSource(**kwargs)
    if model_id in {"faster-whisper", "whisper", "whisper-lg", "whisper-med"}:
        fw_kwargs: dict[str, object] = dict(
            device=effective_device,
            language=effective_language,
            speaker_map=speaker_map,
        )
        if options.compute_type is not None:
            fw_kwargs["compute_type"] = options.compute_type
        if options.beam_size is not None:
            fw_kwargs["beam_size"] = options.beam_size
        if options.num_threads is not None:
            fw_kwargs["num_threads"] = options.num_threads
        return FasterWhisperSource(**fw_kwargs)
    raise ValueError(f"unknown ASR model_id: {model_id!r}")


def list_speech_backends() -> list[str]:
    """Names of available speech backends for UI surface area.

    Returned in the same order as the underlying registry. Exposed
    through ``core`` so UI (argparse ``choices=``, combobox) does not
    need to reach into ``sources/`` directly.
    """

    # Local import — avoids paying the cost of loading every speech
    # backend module just because a caller asked for the list.
    from sources import list_speech_sources

    return list_speech_sources()


def transcribe_one_track(
    source: Source,
    audio_path: Path,
    *,
    speaker: str | None = None,
    on_progress: TrackProgress | None = None,
    should_cancel: CancelProbe | None = None,
) -> list[SpeechSegment]:
    """Run ASR on ``audio_path`` via the given source.

    Thin pass-through to ``source.transcribe_track`` — separating
    dispatch (``make_source``) from per-track invocation lets a batch
    worker hold one source across many tracks without callers
    reaching into backend-specific classes.
    """

    return source.transcribe_track(  # type: ignore[attr-defined]
        audio_path,
        speaker=speaker,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
