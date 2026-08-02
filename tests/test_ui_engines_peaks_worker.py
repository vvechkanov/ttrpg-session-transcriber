"""PeaksWorker: parallel decode, duration-first, resilient to bad files.

Peak extraction is a full ffmpeg decode — ~16 s for a 17 MB track and
minutes for a 200 MB one. Sequentially that left every lane in a
six-track session blank for several minutes, which reads as a hang.
"""

from __future__ import annotations

import sys
import time

from PySide6.QtGui import QGuiApplication

from ui.engines import peaks_worker as pw
from ui.engines.peaks_worker import PeaksWorker


def _ensure_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("peaks-test")
    app.setOrganizationName("peaks-test")
    return app


def _segments(n: int) -> list[tuple[int, int, str]]:
    return [(row, 0, f"/fake/track{row}.flac") for row in range(n)]


def test_decodes_in_parallel(monkeypatch) -> None:
    """Six slow decodes must not take six times one decode."""

    _ensure_app()

    delay = 0.30
    monkeypatch.setattr(pw, "probe_duration", lambda p: 100.0)

    def _slow_peaks(path):
        time.sleep(delay)
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(pw, "get_or_compute_peaks", _slow_peaks)

    worker = PeaksWorker(_segments(6))
    got: list[tuple[int, int]] = []
    worker.peaksReady.connect(lambda r, s, p: got.append((r, s)))

    started = time.perf_counter()
    worker.run()
    elapsed = time.perf_counter() - started

    assert len(got) == 6, f"expected every segment to report, got {got}"
    sequential = delay * 6
    assert elapsed < sequential * 0.6, (
        f"took {elapsed:.2f}s; sequential would be ~{sequential:.2f}s — "
        "the pool is not actually running decodes concurrently"
    )


def test_durations_precede_any_decode(monkeypatch) -> None:
    """The ruler must get its full extent before slow decodes start.

    Probing is a metadata read; emitting all of them up front means the
    ruler stops growing in jerks as each file finishes.
    """

    _ensure_app()

    order: list[str] = []

    def _probe(path):
        order.append("probe")
        return 100.0

    def _peaks(path):
        order.append("decode")
        return [0.5]

    monkeypatch.setattr(pw, "probe_duration", _probe)
    monkeypatch.setattr(pw, "get_or_compute_peaks", _peaks)

    worker = PeaksWorker(_segments(4))
    worker.run()

    assert order[:4] == ["probe"] * 4, order
    assert set(order[4:]) == {"decode"}, order


def test_one_unreadable_file_does_not_kill_the_batch(monkeypatch) -> None:
    """A corrupt track must not cost the other five their waveforms."""

    _ensure_app()

    monkeypatch.setattr(pw, "probe_duration", lambda p: 100.0)

    def _peaks(path):
        if str(path).endswith("track2.flac"):
            raise OSError("corrupt")
        return [0.5]

    monkeypatch.setattr(pw, "get_or_compute_peaks", _peaks)

    worker = PeaksWorker(_segments(4))
    got: list[int] = []
    done: list[bool] = []
    worker.peaksReady.connect(lambda r, s, p: got.append(r))
    worker.allDone.connect(lambda: done.append(True))

    worker.run()

    assert sorted(got) == [0, 1, 3], got
    assert done == [True], "allDone must fire exactly once"
