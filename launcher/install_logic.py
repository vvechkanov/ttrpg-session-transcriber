"""Installation logic for the bootstrap EXE (Epic A / B + C).

Post-migration the installer EXE (``WhisperX-Transcriber.exe``) is a
PyInstaller-frozen Python process, so it can call
``core.backend_installers.install_backend`` **in-process** — no more
embedded Python, no more ``pip install torch|whisperx|sherpa-onnx``,
no more ``get-pip.py``. ASR bundles ship through the Epic A tracked
install path (``%APPDATA%/ttrpg-transcriber/models/<backend>/<slug>/``).

What this module is still responsible for:
    * ffmpeg download into ``DATA_DIR/tools/ffmpeg`` (the runtime EXE
      picks it up via the ``PATH`` environment variable the launcher
      extends before ``Popen``).
    * ``detect_gpu`` — informational banner in the installer UI so the
      user sees "CUDA mode" vs "CPU mode" and understands what the
      runtime will do.
    * ``STEP_WEIGHTS`` — overall progress bar weighting used by
      :mod:`launcher.installer_ui`.

Everything else (PyTorch / WhisperX / get-pip / embeddable Python /
sherpa-onnx pip) was removed — those stacks live inside the ASR
backend bundles themselves now (see
``sources/speech/_fw_download.py`` wheel unpacking).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

#: GitHub repository that hosts the release assets (installer EXE +
#: PySide6 runtime zip). Tag format: ``v{VERSION}``; asset filename:
#: ``session-transcriber.zip``. See ``.github/workflows/release.yml``.
RUNTIME_REPO = "vvechkanov/ttrpg-session-transcriber"
RUNTIME_ASSET = "session-transcriber.zip"

#: Weights for the overall progress bar in :mod:`launcher.installer_ui`.
#: Sum does not matter — UI normalises to 100 %. Weights reflect the
#: *actual time* each stage takes on a mid-range home connection:
#:
#:     * ffmpeg  ~50 MB  ->  10 % (fast CDN)
#:     * models  ~1-3 GB -> 60 % (biggest payload, dominates total time)
#:     * runtime ~80 MB  -> 30 % (session-transcriber.zip from GitHub
#:       Release, downloaded + unzipped by bootstrap)
STEP_WEIGHTS = {
    "ffmpeg": 10,
    "models": 60,
    "runtime": 30,
}

#: Path inside the extracted runtime zip where ``session-transcriber.exe``
#: lives. Matches the ``COLLECT(name=APP_NAME)`` output of the root
#: ``build.spec`` — PyInstaller creates a subdirectory named after
#: ``APP_NAME`` and puts the exe + Qt DLLs inside it.
RUNTIME_EXE_RELPATH = Path("session-transcriber") / "session-transcriber.exe"

LogFn = Callable[[str], None]
ProgressFn = Callable[[float], None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download(
    url: str,
    dest: Path,
    on_log: LogFn,
    on_progress: ProgressFn | None = None,
) -> None:
    """Download a URL to a local file with optional progress updates."""
    on_log(f"Скачивание: {url}")
    req = Request(url, headers={"User-Agent": "WhisperX-Transcriber/1.0"})
    resp = urlopen(req, timeout=120)
    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    chunk_size = 256 * 1024  # 256 KB

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total and on_progress:
                on_progress(downloaded / total * 100)

    on_log(f"Скачано: {dest.name} ({downloaded // 1024} KB)")


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def detect_gpu(on_log: LogFn) -> str:
    """Detect NVIDIA GPU via nvidia-smi. Returns 'cuda' or 'cpu'.

    Informational only — the installer does not install torch/CUDA
    wheels anymore. The ASR backend bundle chooses CPU vs GPU compute
    kernels at runtime based on what the user picks in the settings
    drawer.
    """
    try:
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=10,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                m = re.search(r"(NVIDIA\s+\S+.*?)\s+\|", line)
                if m:
                    on_log(f"GPU обнаружена: {m.group(1).strip()}")
                    break
            return "cuda"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    on_log("NVIDIA GPU не обнаружена — режим CPU (медленнее в 5-10x)")
    return "cpu"


def download_ffmpeg(
    dest_dir: Path, on_log: LogFn, on_progress: ProgressFn
) -> None:
    """Download and extract ffmpeg into ``dest_dir``.

    ``dest_dir`` becomes the top-level ffmpeg directory with
    ``bin/ffmpeg.exe`` inside. If ffmpeg is already present in the
    system ``PATH``, the download is skipped.
    """
    ffmpeg_exe = dest_dir / "bin" / "ffmpeg.exe"
    if ffmpeg_exe.exists():
        on_log(f"ffmpeg уже установлен: {ffmpeg_exe}")
        on_progress(100)
        return

    if shutil.which("ffmpeg"):
        on_log("ffmpeg найден в системном PATH — пропуск загрузки.")
        on_progress(100)
        return

    on_log("Скачивание ffmpeg...")
    on_progress(0)

    tmp_zip = Path(tempfile.gettempdir()) / "ffmpeg-release-essentials.zip"
    _download(
        FFMPEG_URL, tmp_zip, on_log, on_progress=lambda p: on_progress(p * 0.7)
    )

    on_log("Распаковка ffmpeg...")
    on_progress(70)

    tmp_extract = Path(tempfile.gettempdir()) / "ffmpeg_extract"
    if tmp_extract.exists():
        shutil.rmtree(tmp_extract)

    with zipfile.ZipFile(tmp_zip, "r") as zf:
        zf.extractall(tmp_extract)

    subdirs = [d for d in tmp_extract.iterdir() if d.is_dir()]
    if not subdirs:
        raise RuntimeError("Unexpected ffmpeg archive layout")

    top_dir = subdirs[0]

    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.move(str(top_dir), str(dest_dir))

    shutil.rmtree(tmp_extract, ignore_errors=True)
    tmp_zip.unlink(missing_ok=True)

    on_progress(100)
    on_log(f"ffmpeg установлен: {dest_dir}")


def _resolve_runtime_url(version: str) -> str:
    """Build the download URL for the runtime zip of a given version.

    We deliberately bypass the GitHub API (no auth, no rate limits)
    by going straight to the ``releases/download/<tag>/<asset>`` CDN
    path. This fails cleanly with HTTP 404 if the release is missing,
    which is exactly the error we want to surface to the user.
    """
    tag = f"v{version}"
    return (
        f"https://github.com/{RUNTIME_REPO}/releases/download/"
        f"{tag}/{RUNTIME_ASSET}"
    )


def download_runtime_zip(
    data_dir: Path,
    version: str,
    on_log: LogFn,
    on_progress: ProgressFn,
) -> Path:
    """Download and extract the PySide6 runtime bundle.

    Flow:
        1. Download ``session-transcriber.zip`` from the matching
           GitHub Release tag into ``%TMP%``.
        2. Extract it into ``data_dir`` so the final layout is
           ``data_dir/session-transcriber/session-transcriber.exe``.
        3. Wipe any previous ``session-transcriber/`` directory first —
           this makes reinstall/upgrade idempotent.

    Returns:
        Path to the extracted ``session-transcriber.exe``.

    Raises:
        RuntimeError: if the zip layout doesn't contain
            ``session-transcriber.exe`` where expected.
    """
    on_log(f"Загрузка приложения (session-transcriber v{version})...")
    on_progress(0)

    runtime_dir = data_dir / "session-transcriber"
    if runtime_dir.exists():
        on_log(f"Удаление старой версии: {runtime_dir}")
        shutil.rmtree(runtime_dir, ignore_errors=True)

    tmp_zip = Path(tempfile.gettempdir()) / "session-transcriber.zip"
    url = _resolve_runtime_url(version)
    _download(
        url, tmp_zip, on_log, on_progress=lambda p: on_progress(p * 0.8)
    )

    on_log("Распаковка приложения...")
    on_progress(80)

    data_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(tmp_zip, "r") as zf:
        zf.extractall(data_dir)

    tmp_zip.unlink(missing_ok=True)

    runtime_exe = data_dir / RUNTIME_EXE_RELPATH
    if not runtime_exe.exists():
        raise RuntimeError(
            f"session-transcriber.exe не найден после распаковки: "
            f"ожидался {runtime_exe}. Проверьте формат zip-архива в релизе."
        )

    on_progress(100)
    on_log(f"Приложение установлено: {runtime_exe}")
    return runtime_exe
