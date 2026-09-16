"""Tier 1 — core.pipeline._speech_kwargs narrowing tests.

Verifies that _speech_kwargs correctly selects constructor arguments
per backend class. No audio, no models, no subprocess.
Must run in <5s.
"""

import pytest


def _make_params(**overrides):
    """Build PipelineParams with defaults, allowing field overrides."""
    from core.pipeline import PipelineParams
    defaults = dict(
        speech_backend="faster-whisper",
        model="test-model",
        device="cpu",
        compute_type="int8",
        language="ru",
        beam_size=3,
        merger="script",
        renderer="plain-text",
        output_filename="merged.txt",
        speaker_map=None,
    )
    defaults.update(overrides)
    return PipelineParams(**defaults)


class TestSpeechKwargsForFasterWhisper:
    def test_faster_whisper_kwargs_has_no_beam_size(self):
        from core.pipeline import _speech_kwargs
        from sources.speech.faster_whisper import FasterWhisperSource
        params = _make_params(beam_size=5)
        kwargs = _speech_kwargs(params, FasterWhisperSource)
        assert "beam_size" not in kwargs

    def test_faster_whisper_kwargs_has_required_fields(self):
        from core.pipeline import _speech_kwargs
        from sources.speech.faster_whisper import FasterWhisperSource
        params = _make_params(model="my-model", device="cpu", compute_type="int8", language="en")
        kwargs = _speech_kwargs(params, FasterWhisperSource)
        assert kwargs["model"] == "my-model"
        assert kwargs["device"] == "cpu"
        assert kwargs["compute_type"] == "int8"
        assert kwargs["language"] == "en"

    def test_faster_whisper_kwargs_includes_speaker_map(self):
        from core.pipeline import _speech_kwargs
        from sources.speech.faster_whisper import FasterWhisperSource
        smap = {"1-gm": "TestGM"}
        params = _make_params(speaker_map=smap)
        kwargs = _speech_kwargs(params, FasterWhisperSource)
        assert kwargs["speaker_map"] == smap

    def test_faster_whisper_kwargs_speaker_map_none(self):
        from core.pipeline import _speech_kwargs
        from sources.speech.faster_whisper import FasterWhisperSource
        params = _make_params(speaker_map=None)
        kwargs = _speech_kwargs(params, FasterWhisperSource)
        assert kwargs["speaker_map"] is None


class TestSpeechKwargsForGigaAM:
    """GigaAM's branch, which the WhisperX class used to stand in for.

    This file tested the faster-whisper branch and the WhisperX branch and
    left the third untested — the removal made that visible by taking away
    the only test that proved ``_speech_kwargs`` narrows *differently* per
    backend. Without a second live backend under test, deleting the
    ``GigaAMSource`` branch outright would still leave the file green.
    """

    def test_gigaam_kwargs_are_the_gigaam_knobs_and_not_the_whisper_ones(self):
        """Every value here differs from its ``PipelineParams`` default.

        Deliberately: ``variant`` defaults to ``"rnnt"``, ``precision`` to
        ``"fp32"``, ``device`` to ``"cuda"``, ``num_threads`` to ``4``. A
        test that asserted those back could not tell a pass-through from a
        constant, and a branch that hardcoded ``device="cpu"`` — silently
        ignoring a GigaAM user's GPU — would run green. Measured: it did.
        """
        from core.pipeline import _speech_kwargs
        from sources.speech.gigaam import GigaAMSource
        params = _make_params(
            gigaam_variant="e2e_rnnt",
            gigaam_precision="int8",
            device="cuda",
            num_threads=7,
        )
        kwargs = _speech_kwargs(params, GigaAMSource)
        assert kwargs["variant"] == "e2e_rnnt"
        assert kwargs["precision"] == "int8"
        assert kwargs["device"] == "cuda"
        assert kwargs["num_threads"] == 7
        assert "model" not in kwargs
        assert "compute_type" not in kwargs
        assert "beam_size" not in kwargs

    def test_gigaam_kwargs_include_speaker_map(self):
        from core.pipeline import _speech_kwargs
        from sources.speech.gigaam import GigaAMSource
        smap = {"2-player": "Alice (Aragorn)"}
        params = _make_params(speaker_map=smap)
        kwargs = _speech_kwargs(params, GigaAMSource)
        assert kwargs["speaker_map"] == smap


class TestSpeechKwargsUnknownClass:
    def test_unknown_class_raises_value_error(self):
        from core.pipeline import _speech_kwargs
        from sources.base import Source

        class UnknownSource(Source):
            name = "unknown"

            def extract(self, session_dir):
                return []

        params = _make_params()
        with pytest.raises(ValueError, match="unknown speech source class"):
            _speech_kwargs(params, UnknownSource)


class TestPipelineParamsDefaults:
    """Verify PipelineParams default values match documented expectations."""

    def test_default_speech_backend(self):
        from core.pipeline import PipelineParams
        p = PipelineParams()
        assert p.speech_backend == "faster-whisper"

    def test_default_model(self):
        from core.pipeline import PipelineParams
        p = PipelineParams()
        assert p.model == "bzikst/faster-whisper-large-v3-ru-podlodka"

    def test_default_output_filename(self):
        from core.pipeline import PipelineParams
        p = PipelineParams()
        assert p.output_filename == "merged.txt"

    def test_params_are_frozen(self):
        from core.pipeline import PipelineParams
        p = PipelineParams()
        with pytest.raises((AttributeError, TypeError)):
            p.device = "cpu"  # type: ignore[misc]

    def test_default_chunking_is_none(self):
        from core.pipeline import PipelineParams
        p = PipelineParams()
        assert p.chunking is None
