"""
Installation logic — Python port of install_whisperx_windows.ps1.

Every public function accepts on_log(msg) and on_progress(percent) callbacks
so the UI can display real-time progress.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from urllib.request import urlopen, Request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PYTHON_EMBED_URL = (
    "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"
)
PYTHON_EMBED_ZIP = "python-3.12.8-embed-amd64.zip"

GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

TORCH_INDEX_CUDA = "https://download.pytorch.org/whl/cu126"
TORCH_INDEX_CPU = "https://download.pytorch.org/whl/cpu"

WHISPERX_PIP = "whisperx @ git+https://github.com/m-bain/whisperX.git"

# Weighted step percentages for overall progress
STEP_WEIGHTS = {
    "python":   5,
    "pip":      5,
    "pytorch":  55,
    "whisperx": 25,
    "ffmpeg":   10,
}

LogFn = Callable[[str], None]
ProgressFn = Callable[[float], None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path, on_log: LogFn,
              on_progress: ProgressFn | None = None) -> None:
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


def _run_pip(python_exe: Path, args: list[str], *,
             on_log: LogFn, on_progress: ProgressFn | None = None,
             cwd: Path | None = None) -> None:
    """Run pip via python -m pip with real-time output streaming."""
    cmd = [str(python_exe), "-m", "pip"] + args
    on_log(">> " + " ".join(cmd))

    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )

    for line in proc.stdout:  # type: ignore[union-attr]
        line = line.rstrip()
        if not line:
            continue
        on_log(line)
        # Parse pip download progress (e.g. "Downloading ... 45%")
        if on_progress:
            m = re.search(r"(\d+)%", line)
            if m:
                on_progress(float(m.group(1)))

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"pip exited with code {proc.returncode}")


# ---------------------------------------------------------------------------
# Installation steps
# ---------------------------------------------------------------------------

def extract_embedded_python(
    bundle_python_zip: Path,
    dest_dir: Path,
    tkinter_src: Path | None,
    on_log: LogFn,
    on_progress: ProgressFn,
) -> Path:
    """
    Extract the Python embeddable package and configure it for pip/tkinter.

    Args:
        bundle_python_zip: path to python-3.12.x-embed-amd64.zip
        dest_dir: where to extract (e.g. %LOCALAPPDATA%/WhisperX-Transcriber/python)
        tkinter_src: directory with tkinter files (_tkinter.pyd, tcl/, tk/, etc.)

    Returns:
        Path to the extracted python.exe
    """
    on_log("Извлечение Python runtime...")
    on_progress(0)

    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(bundle_python_zip, "r") as zf:
        zf.extractall(dest_dir)
    on_progress(50)

    # Enable site-packages by editing python3XX._pth
    pth_files = list(dest_dir.glob("python*._pth"))
    for pth in pth_files:
        text = pth.read_text(encoding="utf-8")
        text = text.replace("#import site", "import site")
        if "import site" not in text:
            text += "\nimport site\n"
        pth.write_text(text, encoding="utf-8")
        on_log(f"  Enabled site-packages in {pth.name}")

    # Copy tkinter files if provided
    if tkinter_src and tkinter_src.exists():
        on_log("  Копирование tkinter...")
        for item in tkinter_src.iterdir():
            dst = dest_dir / item.name
            if item.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)

    on_progress(100)
    python_exe = dest_dir / "python.exe"
    if not python_exe.exists():
        raise FileNotFoundError(f"python.exe not found in {dest_dir}")

    on_log(f"Python runtime: {python_exe}")
    return python_exe


def download_embedded_python(
    dest_zip: Path, on_log: LogFn, on_progress: ProgressFn
) -> None:
    """Download the Python embeddable package from python.org."""
    if dest_zip.exists():
        on_log(f"Python embeddable уже скачан: {dest_zip.name}")
        on_progress(100)
        return
    _download(PYTHON_EMBED_URL, dest_zip, on_log, on_progress)


def install_pip(python_exe: Path, on_log: LogFn, on_progress: ProgressFn) -> None:
    """Download and run get-pip.py."""
    on_log("Установка pip...")
    on_progress(0)

    get_pip = python_exe.parent / "get-pip.py"
    _download(GET_PIP_URL, get_pip, on_log)
    on_progress(30)

    # Run get-pip.py
    cmd = [str(python_exe), str(get_pip)]
    on_log(">> " + " ".join(cmd))

    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    for line in proc.stdout:  # type: ignore[union-attr]
        line = line.rstrip()
        if line:
            on_log(line)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"get-pip.py exited with code {proc.returncode}")

    on_progress(70)

    # Upgrade pip + setuptools + wheel
    _run_pip(python_exe, ["install", "--upgrade", "pip", "setuptools", "wheel"],
             on_log=on_log)
    on_progress(100)
    on_log("pip установлен.")

    # Clean up get-pip.py
    get_pip.unlink(missing_ok=True)


def detect_gpu(on_log: LogFn) -> str:
    """Detect NVIDIA GPU via nvidia-smi. Returns 'cuda' or 'cpu'."""
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
            # Try to parse GPU name
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


def install_pytorch(
    python_exe: Path, mode: str, on_log: LogFn, on_progress: ProgressFn
) -> None:
    """Install PyTorch (CUDA or CPU)."""
    index_url = TORCH_INDEX_CUDA if mode == "cuda" else TORCH_INDEX_CPU
    label = "CUDA" if mode == "cuda" else "CPU"
    on_log(f"Установка PyTorch ({label})... Это может занять несколько минут.")
    on_progress(0)

    _run_pip(
        python_exe,
        ["install", "--no-cache-dir", "--index-url", index_url,
         "torch", "torchvision", "torchaudio"],
        on_log=on_log,
        on_progress=on_progress,
    )
    on_progress(100)
    on_log(f"PyTorch ({label}) установлен.")


def install_whisperx(
    python_exe: Path, on_log: LogFn, on_progress: ProgressFn
) -> None:
    """Install WhisperX from GitHub."""
    on_log("Установка WhisperX...")
    on_progress(0)

    _run_pip(
        python_exe,
        ["install", "--no-cache-dir", WHISPERX_PIP],
        on_log=on_log,
        on_progress=on_progress,
    )
    on_progress(100)
    on_log("WhisperX установлен.")


def repin_pytorch_cuda(
    python_exe: Path, on_log: LogFn, on_progress: ProgressFn
) -> None:
    """Re-pin PyTorch CUDA wheels after WhisperX (it may pull CPU torch)."""
    on_log("Фиксация PyTorch CUDA...")
    on_progress(0)

    _run_pip(
        python_exe,
        ["install", "--force-reinstall", "--no-cache-dir", "--no-deps",
         "--index-url", TORCH_INDEX_CUDA,
         "torch", "torchvision", "torchaudio"],
        on_log=on_log,
        on_progress=on_progress,
    )
    on_progress(100)


def download_ffmpeg(
    dest_dir: Path, on_log: LogFn, on_progress: ProgressFn
) -> None:
    """Download and extract ffmpeg."""
    ffmpeg_exe = dest_dir / "bin" / "ffmpeg.exe"
    if ffmpeg_exe.exists():
        on_log(f"ffmpeg уже установлен: {ffmpeg_exe}")
        on_progress(100)
        return

    # Check system PATH
    if shutil.which("ffmpeg"):
        on_log("ffmpeg найден в системном PATH — пропуск загрузки.")
        on_progress(100)
        return

    on_log("Скачивание ffmpeg...")
    on_progress(0)

    tmp_zip = Path(tempfile.gettempdir()) / "ffmpeg-release-essentials.zip"
    _download(FFMPEG_URL, tmp_zip, on_log, on_progress=lambda p: on_progress(p * 0.7))

    on_log("Распаковка ffmpeg...")
    on_progress(70)

    tmp_extract = Path(tempfile.gettempdir()) / "ffmpeg_extract"
    if tmp_extract.exists():
        shutil.rmtree(tmp_extract)

    with zipfile.ZipFile(tmp_zip, "r") as zf:
        zf.extractall(tmp_extract)

    # Find the top-level directory inside the archive
    subdirs = [d for d in tmp_extract.iterdir() if d.is_dir()]
    if not subdirs:
        raise RuntimeError("Unexpected ffmpeg archive layout")

    top_dir = subdirs[0]

    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.move(str(top_dir), str(dest_dir))

    # Cleanup
    shutil.rmtree(tmp_extract, ignore_errors=True)
    tmp_zip.unlink(missing_ok=True)

    on_progress(100)
    on_log(f"ffmpeg установлен: {dest_dir}")


def verify_installation(python_exe: Path, on_log: LogFn) -> dict:
    """Verify that torch and whisperx can be imported. Returns diagnostic info."""
    on_log("Проверка установки...")
    result = {"ok": False, "torch": "", "cuda": False, "gpu": "", "whisperx": False}

    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    check_script = (
        "import json, sys\n"
        "d = {'ok': False, 'torch': '', 'cuda': False, 'gpu': '', 'whisperx': False}\n"
        "try:\n"
        "    import torch\n"
        "    d['torch'] = torch.__version__\n"
        "    d['cuda'] = torch.cuda.is_available()\n"
        "    if d['cuda'] and torch.cuda.device_count() > 0:\n"
        "        d['gpu'] = torch.cuda.get_device_name(0)\n"
        "except Exception as e:\n"
        "    d['error_torch'] = str(e)\n"
        "try:\n"
        "    import whisperx\n"
        "    d['whisperx'] = True\n"
        "except Exception as e:\n"
        "    d['error_whisperx'] = str(e)\n"
        "d['ok'] = bool(d['torch'] and d['whisperx'])\n"
        "print(json.dumps(d))\n"
    )

    proc = subprocess.run(
        [str(python_exe), "-c", check_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )

    import json
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            result = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            pass

    if result.get("ok"):
        on_log(f"  torch {result['torch']}  |  CUDA: {result['cuda']}  |  GPU: {result.get('gpu', 'n/a')}")
        on_log("  whisperx OK")
    else:
        on_log(f"  WARN: проверка не пройдена: {result}")

    return result
