"""Unit tests for runtime helpers in sources/speech/gigaam.py.

Covers _pick_decoding_method, _detect_provider, and junk-filter logic
inside _recognize_segment. sherpa_onnx and onnxruntime are fully mocked.
Must run in < 50 ms each. No network, no GPU.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("sherpa_onnx", MagicMock())
sys.modules.setdefault("onnxruntime", MagicMock())


class TestPickDecodingMethod:
    def test_none_returns_greedy(self):
        from sources.speech.gigaam import _pick_decoding_method
        assert _pick_decoding_method(None) == "greedy_search"

    def test_nonexistent_path_returns_greedy(self, tmp_path):
        from sources.speech.gigaam import _pick_decoding_method
        result = _pick_decoding_method(tmp_path / "no_such_file.txt")
        assert result == "greedy_search"

    def test_empty_file_returns_greedy(self, tmp_path):
        from sources.speech.gigaam import _pick_decoding_method
        f = tmp_path / "hotwords.txt"
        f.write_text("", encoding="utf-8")
        assert _pick_decoding_method(f) == "greedy_search"

    def test_whitespace_only_file_returns_greedy(self, tmp_path):
        from sources.speech.gigaam import _pick_decoding_method
        f = tmp_path / "hotwords.txt"
        f.write_text("   \n  \n", encoding="utf-8")
        assert _pick_decoding_method(f) == "greedy_search"

    def test_nonempty_file_returns_beam_search(self, tmp_path):
        from sources.speech.gigaam import _pick_decoding_method
        f = tmp_path / "hotwords.txt"
        f.write_text("двадцатка\nкрит\n", encoding="utf-8")
        assert _pick_decoding_method(f) == "modified_beam_search"


class TestDetectProvider:
    def test_cpu_returns_cpu(self):
        from sources.speech.gigaam import _detect_provider
        assert _detect_provider("cpu") == "cpu"

    def test_cuda_without_provider_falls_back_to_cpu(self, caplog):
        import logging
        import importlib

        fake_ort = MagicMock()
        fake_ort.get_available_providers.return_value = ["CPUExecutionProvider"]

        with patch.dict(sys.modules, {"onnxruntime": fake_ort}):
            # Re-import to pick up mock
            import sources.speech.gigaam as mod
            importlib.reload(mod)

            with caplog.at_level(logging.WARNING, logger="sources.speech.gigaam"):
                result = mod._detect_provider("cuda")

        assert result == "cpu"
        assert any("fallback" in r.message.lower() or "cpu" in r.message.lower()
                   for r in caplog.records if r.levelno == logging.WARNING)

    def test_cuda_with_cuda_provider_returns_cuda(self):
        import importlib

        fake_ort = MagicMock()
        fake_ort.get_available_providers.return_value = [
            "CPUExecutionProvider",
            "CUDAExecutionProvider",
        ]

        with patch.dict(sys.modules, {"onnxruntime": fake_ort}):
            import sources.speech.gigaam as mod
            importlib.reload(mod)
            result = mod._detect_provider("cuda")

        assert result == "cuda"


class TestJunkFilter:
    """Tests for junk-filter logic extracted from _recognize_segment."""

    def _make_source(self):
        from sources.speech.gigaam import GigaAMSource
        src = GigaAMSource.__new__(GigaAMSource)
        # Minimal init without calling __init__ (avoids sherpa_onnx)
        src._recognizer = MagicMock()
        src._vad = MagicMock()
        return src

    def _make_speech(self, samples_len: int, start: int = 0):
        import numpy as np
        speech = MagicMock()
        speech.samples = np.zeros(samples_len, dtype="float32")
        speech.start = start
        return speech

    def _stub_recognizer(self, src, text: str):
        stream = MagicMock()
        stream.result.text = text
        src._recognizer.create_stream.return_value = stream

    def test_short_text_dropped(self):
        src = self._make_source()
        self._stub_recognizer(src, "а")  # 1 char < 2
        speech = self._make_speech(16000)  # 1 sec
        result = src._recognize_segment(speech, "Speaker")
        assert result is None

    def test_empty_text_dropped(self):
        src = self._make_source()
        self._stub_recognizer(src, "")
        speech = self._make_speech(16000)
        assert src._recognize_segment(speech, "Speaker") is None

    def test_low_density_on_long_segment_dropped(self):
        # 3 sec @ 16kHz = 48000 samples, 1 char / 3 sec = 0.33 < 0.5 threshold
        src = self._make_source()
        self._stub_recognizer(src, "а")  # 1 char but >= 2... wait, 1 < 2 so it's short
        # Use 2 chars to pass the length gate, still low density on 3s
        self._stub_recognizer(src, "аб")  # 2 chars, 3 sec → 0.67 chars/sec > 0.5
        speech = self._make_speech(48000)  # 3 sec
        # 0.67 > 0.5 so it should PASS
        result = src._recognize_segment(speech, "Speaker")
        assert result is not None

    def test_very_low_density_long_segment_dropped(self):
        # 10 sec, 2 chars → 0.2 chars/sec < 0.5
        src = self._make_source()
        self._stub_recognizer(src, "аб")  # 2 chars
        speech = self._make_speech(160000)  # 10 sec @ 16kHz
        result = src._recognize_segment(speech, "Speaker")
        assert result is None

    def test_normal_text_passes(self):
        src = self._make_source()
        self._stub_recognizer(src, "двадцатка")  # 9 chars
        speech = self._make_speech(16000)  # 1 sec → 9 chars/sec, fine
        result = src._recognize_segment(speech, "Speaker")
        assert result is not None
        assert result.text == "двадцатка"

    def test_segment_fields_correct(self):
        import numpy as np
        src = self._make_source()
        self._stub_recognizer(src, "тест")
        # 8000 samples @ 16kHz = 0.5 sec, starting at sample 16000 (1.0 sec offset)
        speech = self._make_speech(8000, start=16000)
        result = src._recognize_segment(speech, "Alice")
        assert result is not None
        assert result.start == pytest.approx(1.0)
        assert result.end == pytest.approx(1.5)
        assert result.speaker == "Alice"
        assert result.confidence is None
