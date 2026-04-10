#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch-run whisperx on a folder of per-speaker Craig tracks (e.g. *.flac),
then (optionally) merge produced *.json into a single merged.txt (LLM-friendly).

Typical usage:
  python wisper_launcher.py .\\games\\bogomols\\11.07.2025 --device cuda --compute_type float16 --hf_token YOUR_TOKEN --merge
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path

# Suppress noisy torchcodec / pyannote warnings at import time
warnings.filterwarnings("ignore", message=".*torchcodec.*")
warnings.filterwarnings("ignore", message=".*libtorchcodec.*")
os.environ.setdefault("TORCHAUDIO_NO_BACKEND_CHECK", "1")

EXCLUDE_AUDIO_PREFIXES = ("craig",)

# Ensure sibling modules (parse_fvtt_chat) are importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

def _project_root() -> Path:
    """Project root = parent of the scripts/ folder that contains this file."""
    return Path(__file__).resolve().parent.parent


def _inject_local_paths_into_env() -> None:
    """
    Make the launcher robust even when started not via our .bat wrappers.
    Ensures:
    - ffmpeg is discoverable  (<project_root>/tools/ffmpeg/bin)
    - whisperx.exe is discoverable (<project_root>/venv/Scripts)
    - PYTHONIOENCODING=utf-8 so Cyrillic output doesn't crash on Windows
    """
    root = _project_root()

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    parts: list[str] = []

    venv_scripts = root / "venv" / "Scripts"
    if venv_scripts.is_dir():
        parts.append(str(venv_scripts))

    ffmpeg_bin = root / "tools" / "ffmpeg" / "bin"
    if ffmpeg_bin.is_dir():
        parts.append(str(ffmpeg_bin))

    if parts:
        os.environ["PATH"] = ";".join(parts + [os.environ.get("PATH", "")])


def _scan_audio_files(session_dir: Path, pattern: str = "*.flac") -> list[str]:
    """Return sorted list of audio file stems, excluding craig tracks."""
    return sorted(
        p.stem
        for p in session_dir.glob(pattern)
        if not any(p.stem.lower() == x or p.stem.lower().startswith(x + "-") for x in EXCLUDE_AUDIO_PREFIXES)
    )


def _find_speaker_map(session_dir: Path) -> Path | None:
    """Find speaker_map.json: first in session dir, then in project root."""
    candidates = [
        session_dir / "speaker_map.json",
        _project_root() / "speaker_map.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_speaker_map(path: Path) -> dict:
    """Load speaker_map.json, return empty dict on failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_speaker_map(data: dict, path: Path) -> None:
    """Save speaker map data as JSON."""
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run(cmd: list[str], *, dry_run: bool = False) -> None:
    printable = " ".join([str(c) for c in cmd])
    print(">>", printable)
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def main() -> int:
    _inject_local_paths_into_env()
    # Double-click UX: no args -> small UI to choose a folder and run.
    if len(sys.argv) == 1:
        return gui_main()

    ap = argparse.ArgumentParser(prog="wisper_launcher.py")
    ap.add_argument("session_dir", help="Folder with Craig per-speaker audio tracks (flac/wav/mp3)")
    ap.add_argument("--pattern", default="*.flac", help="Which audio files to process (default: *.flac)")

    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--language", default="ru")
    ap.add_argument("--device", default=None, help="e.g. cuda / cpu (default: whisperx default)")
    ap.add_argument("--compute_type", default=None, help="e.g. float16 / int8 (default: whisperx default)")
    ap.add_argument("--beam_size", type=int, default=10, help="Beam size for decoding (default: 10)")
    ap.add_argument("--vad_method", default="silero", choices=["pyannote", "silero"], help="VAD method (default: silero)")
    ap.add_argument("--hf_token", default=None, help="HuggingFace token (needed for diarization)")
    ap.add_argument("--diarize", action="store_true", help="Enable whisperx diarization")

    ap.add_argument("--output_dir", default=None, help="Where to write whisperx outputs (default: session_dir)")
    ap.add_argument("--merge", action="store_true", help="After transcription, run merge_whisperx.py")
    ap.add_argument("--merge_only", action="store_true", help="Skip whisperx and only merge existing json files")
    ap.add_argument("--chunk", action="store_true", help="After merge, split merged.txt into overlapping chunks")
    ap.add_argument("--chunk_chars", type=int, default=40000, help="Chunk target size in characters (default: 40000)")
    ap.add_argument("--chunk_overlap", type=float, default=0.20, help="Chunk overlap ratio (default: 0.20)")
    ap.add_argument("--dry_run", action="store_true", help="Print commands without executing")

    args = ap.parse_args()

    session_dir = Path(args.session_dir).expanduser().resolve()
    if not session_dir.exists():
        print(f">>> session_dir not found: {session_dir}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else session_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    produced_jsons: list[Path] = []

    if not args.merge_only:
        audio_files = [
            p
            for p in sorted(session_dir.glob(args.pattern))
            if not any(p.stem.lower() == x or p.stem.lower().startswith(x + "-") for x in EXCLUDE_AUDIO_PREFIXES)
        ]
        if not audio_files:
            print(f">>> No files matched: {session_dir}\\{args.pattern} (excluding: {EXCLUDE_AUDIO_PREFIXES})", file=sys.stderr)
            return 2

        for audio in audio_files:
            cmd: list[str] = ["whisperx", str(audio)]
            cmd += ["--model", args.model]
            cmd += ["--language", args.language]
            cmd += ["--output_dir", str(output_dir)]
            cmd += ["--vad_method", args.vad_method]

            if args.device:
                cmd += ["--device", args.device]
            if args.compute_type:
                cmd += ["--compute_type", args.compute_type]
            if args.beam_size:
                cmd += ["--beam_size", str(args.beam_size)]
            if args.diarize:
                cmd += ["--diarize"]
            if args.hf_token:
                cmd += ["--hf_token", args.hf_token]

            run(cmd, dry_run=args.dry_run)

            # whisperx writes "<stem>.json" in output_dir by default
            produced = output_dir / f"{audio.stem}.json"
            if args.dry_run:
                produced_jsons.append(produced)
            elif produced.exists():
                produced_jsons.append(produced)
            else:
                # don't fail hard: whisperx might be configured differently; we'll fallback to scanning later
                print(f">>> warning: expected json not found yet: {produced}")

    if args.merge:
        merge_script = (Path(__file__).resolve().parent / "merge_whisperx.py").resolve()
        if not merge_script.exists():
            print(f">>> merge script not found: {merge_script}", file=sys.stderr)
            return 2

        jsons = produced_jsons or sorted(output_dir.glob("*.json"))
        if not jsons:
            print(f">>> no json files found in: {output_dir}", file=sys.stderr)
            return 2

        # Run merge in output_dir so merged.md / merged.srt land there
        cmd = [sys.executable, str(merge_script), *[str(p) for p in jsons]]
        print(f"\n== Merging {len(jsons)} transcripts into {output_dir}\\merged.txt")
        if args.dry_run:
            print(">> (cwd)", str(output_dir))
            print(">>", " ".join(cmd))
        else:
            subprocess.run(cmd, cwd=str(output_dir), check=True)

        if args.chunk:
            chunk_script = (Path(__file__).resolve().parent / "chunk_text.py").resolve()
            merged_txt = output_dir / "merged.txt"
            if not merged_txt.exists():
                print(f">>> merged.txt not found for chunking: {merged_txt}", file=sys.stderr)
                return 2
            chunk_cmd = [
                sys.executable,
                str(chunk_script),
                str(merged_txt),
                "--chunk_chars",
                str(args.chunk_chars),
                "--overlap",
                str(args.chunk_overlap),
            ]
            print(f"\n== Chunking merged.txt into: {output_dir}\\chunks")
            if args.dry_run:
                print(">> (cwd)", str(output_dir))
                print(">>", " ".join(chunk_cmd))
            else:
                subprocess.run(chunk_cmd, cwd=str(output_dir), check=True)

    return 0


def _detect_gpu() -> dict:
    """Check CUDA/GPU availability via PyTorch. Returns a dict with diagnostic info."""
    info: dict = {
        "cuda_available": False,
        "device_count": 0,
        "gpu_name": "",
        "gpu_mem_mb": 0,
        "torch_version": "",
        "cuda_version": "",
        "error": "",
    }
    try:
        import torch
        info["torch_version"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if info["cuda_available"]:
            info["cuda_version"] = torch.version.cuda or ""
            info["device_count"] = torch.cuda.device_count()
            if info["device_count"] > 0:
                info["gpu_name"] = torch.cuda.get_device_name(0)
                mem = torch.cuda.get_device_properties(0).total_memory
                info["gpu_mem_mb"] = mem // (1024 * 1024)
    except ImportError:
        info["error"] = "PyTorch не установлен"
    except Exception as e:
        info["error"] = str(e)
    return info


def _format_gpu_status(info: dict) -> tuple[str, str]:
    """Return (status_text, color) for the GPU info label."""
    if info["error"]:
        return f"[!] {info['error']}", "#cc0000"
    if not info["cuda_available"]:
        return (
            f"[CPU] CUDA недоступна  (torch {info['torch_version']})\n"
            "WhisperX будет работать на CPU — это в ~5-10x медленнее.",
            "#cc6600",
        )
    return (
        f"[GPU] {info['gpu_name']}  ({info['gpu_mem_mb']} MB)  |  "
        f"CUDA {info['cuda_version']}  |  torch {info['torch_version']}",
        "#007700",
    )


def _quick_cuda_test() -> tuple[bool, str]:
    """Actually allocate a tensor on GPU. Returns (success, message)."""
    try:
        import torch
        t = torch.zeros(1, device="cuda")
        del t
        torch.cuda.empty_cache()
        return True, "CUDA тест пройден — GPU работает"
    except Exception as e:
        return False, f"CUDA тест провален: {e}"


def _subprocess_kwargs() -> dict:
    """Extra kwargs to hide console windows on Windows."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def gui_main() -> int:
    """
    Minimal Windows GUI for double-click runs.
    Select a session folder -> (if needed) run whisperx -> merge to merged.txt.
    """
    try:
        import tkinter as tk
        from tkinter import ttk
        from tkinter import filedialog, messagebox
    except Exception as e:
        print(">>> tkinter not available:", e, file=sys.stderr)
        return 2

    root = tk.Tk()
    root.title("WhisperX — Транскрипция сессий")
    root.geometry("780x780")
    root.minsize(600, 500)

    session_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="Выберите папку сессии (где лежат *.flac).")
    merge_only_var = tk.BooleanVar(value=False)
    chunk_var = tk.BooleanVar(value=True)
    chunk_chars_var = tk.StringVar(value="40000")
    chunk_overlap_var = tk.StringVar(value="0.20")
    model_var = tk.StringVar(value="large-v3")
    compute_type_var = tk.StringVar(value="float16")
    beam_size_var = tk.StringVar(value="10")

    # ── FVTT chat log vars ─────────────────────────────────────────────
    chat_log_var = tk.BooleanVar(value=False)
    chat_log_path_var = tk.StringVar(value="")
    chat_tz_var = tk.StringVar(value="auto")

    # ── GPU diagnostics ───────────────────────────────────────────────────
    gpu_info = _detect_gpu()
    device_var = tk.StringVar(value="cuda" if gpu_info["cuda_available"] else "cpu")

    speaker_rows: list[dict] = []
    speaker_status_var = tk.StringVar(value="")
    _running = threading.Event()  # set while worker is active

    # ── Thread-safe logging via queue ─────────────────────────────────────

    _log_queue: queue.Queue[str] = queue.Queue()

    def log(msg: str) -> None:
        """Thread-safe: puts message in queue, polled by main thread."""
        _log_queue.put(msg)

    def _poll_log_queue() -> None:
        """Drain the log queue into the Text widget (runs on main thread)."""
        while True:
            try:
                msg = _log_queue.get_nowait()
            except queue.Empty:
                break
            txt.insert("end", msg + "\n")
            txt.see("end")
        root.after(100, _poll_log_queue)

    def _set_status(msg: str) -> None:
        """Thread-safe status bar update."""
        root.after(0, lambda: status_var.set(msg))

    def _set_progress(value: float, maximum: float = 100) -> None:
        """Thread-safe progress bar update (0..maximum)."""
        root.after(0, lambda: (
            progress_bar.config(maximum=maximum),
            progress_var.set(value),
        ))

    def run_and_stream(cmd: list[str], *, cwd: Path | None = None,
                       status_prefix: str = "") -> str:
        """Run a subprocess with real-time line streaming into log().
        Returns combined stdout+stderr as a string (for GPU marker parsing).
        Raises CalledProcessError on non-zero exit."""
        log(">> " + " ".join(cmd))
        collected: list[str] = []
        p = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_kwargs(),
        )
        for line in p.stdout:  # type: ignore[union-attr]
            stripped = line.rstrip()
            if stripped:
                log("   " + stripped)
                collected.append(stripped)
                # Detect whisperx sub-stages for status bar
                if status_prefix:
                    low = stripped.lower()
                    if "loading" in low and "model" in low:
                        _set_status(f"{status_prefix} — загрузка модели…")
                    elif "transcribing" in low or "transcription" in low:
                        _set_status(f"{status_prefix} — транскрипция…")
                    elif "alignment" in low or "aligning" in low:
                        _set_status(f"{status_prefix} — выравнивание…")
                    elif "diarization" in low or "diarize" in low:
                        _set_status(f"{status_prefix} — диаризация…")
        p.wait()
        if p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, cmd)
        return "\n".join(collected)

    # ── Speaker map helpers ────────────────────────────────────────────────

    def _rebuild_speaker_table(stems: list[str], smap: dict) -> None:
        speaker_rows.clear()
        for w in speaker_table.winfo_children():
            w.destroy()
        for stem in stems:
            entry = smap.get(stem, {})
            if not isinstance(entry, dict):
                entry = {}
            row_frame = ttk.Frame(speaker_table)
            row_frame.pack(fill="x", pady=2)
            player_var = tk.StringVar(value=entry.get("player", ""))
            char_var = tk.StringVar(value=entry.get("character", ""))
            role_var = tk.StringVar(value=entry.get("role", "PC"))
            ttk.Label(row_frame, text=stem, width=20, anchor="w").pack(side="left")
            ttk.Entry(row_frame, textvariable=player_var, width=15,
                      font=("Segoe UI", 9)).pack(side="left", padx=4)
            ttk.Entry(row_frame, textvariable=char_var, width=15,
                      font=("Segoe UI", 9)).pack(side="left", padx=4)
            ttk.Combobox(
                row_frame, textvariable=role_var, values=["PC", "GM"], width=5, state="readonly"
            ).pack(side="left", padx=4)
            speaker_rows.append({
                "stem": stem,
                "player_var": player_var,
                "char_var": char_var,
                "role_var": role_var,
            })

    def _collect_speaker_data() -> dict:
        data = {}
        for row in speaker_rows:
            player = row["player_var"].get().strip()
            char = row["char_var"].get().strip()
            role = row["role_var"].get().strip() or "PC"
            if player or char:
                data[row["stem"]] = {"player": player, "character": char, "role": role}
        return data

    def _on_folder_changed(session_dir: Path) -> None:
        stems = _scan_audio_files(session_dir)
        map_path = _find_speaker_map(session_dir)
        smap = _load_speaker_map(map_path) if map_path else {}
        if map_path:
            loc = "папки сессии" if map_path.parent.resolve() == session_dir.resolve() else "папки проекта"
            speaker_status_var.set(f"Загружен из {loc}")
        elif stems:
            speaker_status_var.set("speaker_map.json не найден — заполните поля")
        else:
            speaker_status_var.set("Аудиофайлы не найдены")
        _rebuild_speaker_table(stems, smap)

        # ── Auto-detect FVTT chat log ──────────────────────────────────
        fvtt_logs = sorted(session_dir.glob("fvtt-log-*.txt"))
        info_path = session_dir / "info.txt"
        if fvtt_logs:
            chat_log_path_var.set(str(fvtt_logs[0]))
            chat_log_var.set(True)
            # Auto-detect timezone if info.txt is available
            if info_path.exists():
                try:
                    from parse_fvtt_chat import (
                        parse_fvtt_log, parse_info_start_time, guess_tz_offset,
                    )
                    entries = parse_fvtt_log(fvtt_logs[0])
                    rec_start = parse_info_start_time(info_path)
                    tz = guess_tz_offset(entries, rec_start)
                    chat_tz_var.set(str(int(tz)))
                except Exception:
                    chat_tz_var.set("auto")
        else:
            chat_log_path_var.set("")
            chat_log_var.set(False)
            chat_tz_var.set("auto")

    def pick_folder() -> None:
        d = filedialog.askdirectory(title="Выберите папку сессии")
        if d:
            session_var.set(d)
            _on_folder_changed(Path(d).resolve())

    def load_map_file() -> None:
        f = filedialog.askopenfilename(
            title="Выберите speaker_map.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if f:
            smap = _load_speaker_map(Path(f))
            if not smap:
                messagebox.showwarning("Пусто", "Файл пуст или повреждён.")
                return
            stems = [r["stem"] for r in speaker_rows] or list(smap.keys())
            _rebuild_speaker_table(stems, smap)
            speaker_status_var.set(f"Загружен: {Path(f).name}")

    def save_map() -> None:
        data = _collect_speaker_data()
        if not data:
            messagebox.showwarning("Пусто", "Нет данных для сохранения — заполните хотя бы одно поле.")
            return
        save_path = _project_root() / "speaker_map.json"
        # Merge with existing data to preserve entries for absent players
        existing = _load_speaker_map(save_path) if save_path.exists() else {}
        existing.update(data)
        _save_speaker_map(existing, save_path)
        speaker_status_var.set(f"Сохранён: {save_path.name}")

    # ── Start pipeline ─────────────────────────────────────────────────────

    def _fmt_elapsed(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        return f"{m}м {s:02d}с" if m else f"{s}с"

    def start() -> None:
        """Validate inputs on main thread, then launch worker thread."""
        if _running.is_set():
            return

        session_dir = Path(session_var.get()).expanduser().resolve()
        if not session_dir.exists():
            messagebox.showerror("Ошибка", "Папка не найдена.")
            return

        # Auto-save speaker map if any fields are filled
        speaker_data = _collect_speaker_data()
        if speaker_data:
            save_path = _project_root() / "speaker_map.json"
            existing = _load_speaker_map(save_path) if save_path.exists() else {}
            existing.update(speaker_data)
            _save_speaker_map(existing, save_path)
            log(f"Speaker map сохранён: {save_path}")

        # Snapshot all UI values before spawning thread (tkinter is not thread-safe)
        params = {
            "session_dir": session_dir,
            "merge_only": merge_only_var.get(),
            "model": model_var.get().strip() or "large-v3",
            "device": device_var.get().strip() or "cuda",
            "compute_type": compute_type_var.get().strip() or "float16",
            "beam_size": max(1, int(beam_size_var.get().strip() or "5")),
            "do_chunk": chunk_var.get(),
            "chunk_chars": int(chunk_chars_var.get().strip() or "40000"),
            "chunk_overlap": float(chunk_overlap_var.get().strip().replace(",", ".") or "0.20"),
            "chat_log_enabled": chat_log_var.get(),
            "chat_log_path": chat_log_path_var.get().strip(),
            "chat_tz_offset": chat_tz_var.get().strip(),
        }

        _running.set()
        btn_start.config(state="disabled", text="⏳ Работаю…")
        progress_var.set(0)
        status_var.set("Запуск…")
        txt.delete("1.0", "end")
        threading.Thread(target=_worker, args=(params,), daemon=True).start()

    def _worker(p: dict) -> None:
        """Heavy pipeline — runs in a background thread."""
        t_total = time.time()
        try:
            _do_pipeline(p)
            elapsed = _fmt_elapsed(time.time() - t_total)
            log(f"\n{'═' * 50}")
            log(f"✅ Всё готово!  Общее время: {elapsed}")
            log(f"   Результат: {p['session_dir']}\\merged.txt")
            _set_status(f"✅ Готово за {elapsed}")
            _set_progress(100, 100)
            root.after(0, lambda: messagebox.showinfo(
                "Готово", f"Сделано за {elapsed}:\n{p['session_dir']}\\merged.txt"))
        except subprocess.CalledProcessError as e:
            log(f"\n❌ Команда завершилась с ошибкой (код {e.returncode})")
            _set_status("❌ Ошибка выполнения")
            root.after(0, lambda: messagebox.showerror(
                "Ошибка WhisperX", f"Команда завершилась с ошибкой:\n{e}"))
        except Exception as e:
            log(f"\n❌ Ошибка: {e}")
            _set_status(f"❌ {e}")
            root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))
        finally:
            _running.clear()
            root.after(0, lambda: btn_start.config(state="normal", text="▶ Запустить"))

    def _do_pipeline(p: dict) -> None:
        """Actual pipeline logic (called from worker thread)."""
        session_dir = p["session_dir"]
        output_dir = session_dir
        merge_script = (Path(__file__).resolve().parent / "merge_whisperx.py").resolve()

        jsons = sorted(output_dir.glob("*.json"))
        need_whisperx = not p["merge_only"] and len(jsons) == 0

        if need_whisperx:
            audio_files = [
                af for af in sorted(session_dir.glob("*.flac"))
                if not any(af.stem.lower() == x or af.stem.lower().startswith(x + "-")
                           for x in EXCLUDE_AUDIO_PREFIXES)
            ]
            if not audio_files:
                raise RuntimeError("В папке нет *.flac (или всё исключено как craig*).")

            device = p["device"]
            model = p["model"]
            compute_type = p["compute_type"]
            beam_size = p["beam_size"]

            # ── GPU pre-flight check ──────────────────────────────────
            if device == "cuda":
                _set_status("Проверка GPU…")
                log("\n🔍 Проверка GPU перед запуском…")
                ok, msg = _quick_cuda_test()
                if ok:
                    log(f"   ✓ {msg}")
                else:
                    log(f"   ⚠️ {msg}")
                    log("   ⚠️ Переключаюсь на CPU!")
                    device = "cpu"

            log(f"\n{'═' * 50}")
            log(f"== Устройство: {device.upper()}  |  model: {model}"
                f"  |  compute: {compute_type}  |  beam: {beam_size}")
            log(f"== Файлов: {len(audio_files)}")
            log(f"{'═' * 50}")

            total_files = len(audio_files)
            _set_progress(0, total_files)
            gpu_confirmed = False
            for idx, audio in enumerate(audio_files, 1):
                t_file = time.time()
                prefix = f"[{idx}/{total_files}] {audio.stem}"
                _set_status(f"{prefix} — запуск…")
                log(f"\n[{idx}/{total_files}] 🎙 {audio.name}")

                cmd = [
                    "whisperx", str(audio),
                    "--model", model,
                    "--language", "ru",
                    "--output_dir", str(output_dir),
                    "--vad_method", "silero",
                    "--device", device,
                    "--compute_type", compute_type,
                    "--beam_size", str(beam_size),
                ]
                output = run_and_stream(cmd, cwd=output_dir,
                                        status_prefix=prefix)

                # ── Parse GPU markers from whisperx output ────────
                low = output.lower()
                if "cuda" in low or "gpu" in low:
                    gpu_confirmed = True
                if device == "cuda" and ("using cpu" in low or "fallback" in low):
                    log("   ⚠️ WhisperX сообщает о работе на CPU!")

                elapsed = _fmt_elapsed(time.time() - t_file)
                log(f"   ✓ Готово за {elapsed}")
                _set_progress(idx, total_files)

            # ── Post-transcription GPU summary ────────────────────
            if device == "cuda":
                if gpu_confirmed:
                    log("\n✓ GPU использовался при транскрипции")
                else:
                    log("\n⚠️ Не удалось подтвердить использование GPU"
                        " (WhisperX не вывел маркеров cuda/gpu)")

        # ── Merge ─────────────────────────────────────────────────
        jsons = sorted(output_dir.glob("*.json"))
        if not jsons:
            raise RuntimeError("Не найдено ни одного *.json для склейки.")

        chat_label = ""
        if p.get("chat_log_enabled") and p.get("chat_log_path"):
            chat_label = " + чат FVTT"
        _set_status(f"Склейка {len(jsons)} JSON{chat_label} → merged.txt…")
        log(f"\n== Склейка {len(jsons)} JSON{chat_label} → merged.txt")
        t_merge = time.time()
        cmd = [sys.executable, str(merge_script), *[str(j) for j in jsons]]
        if p.get("chat_log_enabled") and p.get("chat_log_path"):
            cmd += ["--chat_log", p["chat_log_path"]]
            info_path = Path(p["session_dir"]) / "info.txt"
            if info_path.exists():
                cmd += ["--info_file", str(info_path)]
            tz_val = p.get("chat_tz_offset", "auto")
            if tz_val and tz_val != "auto":
                # Parse "UTC+3" or raw number
                tz_str = str(tz_val).replace("UTC", "").replace("+", "")
                try:
                    cmd += ["--tz_offset", str(float(tz_str))]
                except ValueError:
                    pass  # auto-detect in merge script
        run_and_stream(cmd, cwd=output_dir)
        log(f"   ✓ Готово за {_fmt_elapsed(time.time() - t_merge)}")

        # ── Chunk ─────────────────────────────────────────────────
        if p["do_chunk"]:
            chunk_script = (Path(__file__).resolve().parent / "chunk_text.py").resolve()
            merged_txt = output_dir / "merged.txt"
            if not merged_txt.exists():
                raise RuntimeError("После склейки не найден merged.txt")

            _set_status("Нарезка на чанки…")
            log("\n== Нарезка на чанки")
            t_chunk = time.time()
            chunk_cmd = [
                sys.executable, str(chunk_script), str(merged_txt),
                "--chunk_chars", str(p["chunk_chars"]),
                "--overlap", str(p["chunk_overlap"]),
            ]
            run_and_stream(chunk_cmd, cwd=output_dir)
            log(f"   ✓ Готово за {_fmt_elapsed(time.time() - t_chunk)}")

    # ── Theme / colours ──────────────────────────────────────────────────

    BG       = "#1e1e2e"   # main background
    BG2      = "#2a2a3c"   # card / group background
    FG       = "#cdd6f4"   # default text
    FG_DIM   = "#6c7086"   # muted text
    ACCENT   = "#40b87c"   # green accent (buttons, GPU ok)
    WARN     = "#f9a825"   # orange warnings
    ERR      = "#f44336"   # red errors
    INPUT_BG = "#313244"   # entry / combo background
    INPUT_FG = "#cdd6f4"

    root.configure(bg=BG)

    style = ttk.Style()
    style.theme_use("clam")  # best base for custom colours

    style.configure(".", background=BG, foreground=FG, fieldbackground=INPUT_BG,
                     borderwidth=0, focuscolor=ACCENT)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TFrame", background=BG)
    style.configure("TSeparator", background="#45475a")
    style.configure("TLabelframe", background=BG2, foreground=FG)
    style.configure("TLabelframe.Label", background=BG, foreground=FG_DIM, font=("Segoe UI", 9))
    style.configure("TCheckbutton", background=BG, foreground=FG)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("TCombobox", fieldbackground=INPUT_BG, foreground=INPUT_FG,
                     selectbackground=ACCENT, selectforeground="#fff",
                     arrowcolor=FG_DIM, borderwidth=1)
    style.map("TCombobox",
              fieldbackground=[("readonly", INPUT_BG), ("disabled", BG2)],
              foreground=[("readonly", INPUT_FG), ("disabled", FG_DIM)],
              selectbackground=[("readonly", INPUT_BG)],
              selectforeground=[("readonly", INPUT_FG)],
              arrowcolor=[("readonly", FG_DIM)])
    # Force the Combobox dropdown (Listbox) colours via option_add
    root.option_add("*TCombobox*Listbox.background", INPUT_BG)
    root.option_add("*TCombobox*Listbox.foreground", INPUT_FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#fff")
    style.configure("TEntry", fieldbackground=INPUT_BG, foreground=INPUT_FG)

    # Accent button (green)
    style.configure("Accent.TButton", background=ACCENT, foreground="#fff",
                     font=("Segoe UI", 10, "bold"), padding=(16, 6))
    style.map("Accent.TButton",
              background=[("active", "#36a06a"), ("disabled", "#555")])

    # Link-style button (text only)
    style.configure("Link.TButton", background=BG2, foreground=ACCENT,
                     font=("Segoe UI", 9), padding=(8, 4), borderwidth=0)
    style.map("Link.TButton", foreground=[("active", "#5fd9a0")])

    # Small green outlined button
    style.configure("Outline.TButton", background=BG2, foreground=ACCENT,
                     font=("Segoe UI", 9), padding=(8, 3), borderwidth=1, relief="solid")
    style.map("Outline.TButton", foreground=[("active", "#5fd9a0")])

    # Bold header label
    style.configure("Header.TLabel", font=("Segoe UI", 8, "bold"), foreground=FG_DIM)

    # GPU status bar styles
    style.configure("GpuOk.TLabel", background="#1a3d2a", foreground=ACCENT,
                     font=("Segoe UI", 9, "bold"), padding=(10, 6))
    style.configure("GpuWarn.TLabel", background="#3d3a1a", foreground=WARN,
                     font=("Segoe UI", 9, "bold"), padding=(10, 6))
    style.configure("GpuErr.TLabel", background="#3d1a1a", foreground=ERR,
                     font=("Segoe UI", 9, "bold"), padding=(10, 6))

    # Status text
    style.configure("Dim.TLabel", foreground=FG_DIM, background=BG)

    # Status bar (bottom, prominent)
    style.configure("StatusBar.TLabel", background="#181825", foreground=ACCENT,
                     font=("Segoe UI", 9, "bold"), padding=(10, 6))

    # Progress bar — thick, visible
    style.configure("pointed.Horizontal.TProgressbar",
                     troughcolor=INPUT_BG, background=ACCENT,
                     darkcolor=ACCENT, lightcolor="#5fd9a0", bordercolor=BG2,
                     thickness=10)

    # Section title
    style.configure("Title.TLabel", background=BG, foreground=FG,
                     font=("Segoe UI", 14, "bold"))

    # ── Layout ─────────────────────────────────────────────────────────────

    frm = ttk.Frame(root)
    frm.pack(fill="x", padx=14, pady=(10, 4))

    # ── Title ─────────────────────────────────────────────────────────────

    title_row = ttk.Frame(frm)
    title_row.pack(fill="x", pady=(0, 6))
    ttk.Label(title_row, text="WhisperX", style="Title.TLabel").pack(side="left")
    ttk.Label(title_row, text="  Транскрипция сессий",
              foreground=FG_DIM, font=("Segoe UI", 10)).pack(side="left", pady=(4, 0))

    ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=(0, 8))

    # ── Session folder ────────────────────────────────────────────────────

    ttk.Label(frm, text="Папка сессии:").pack(anchor="w")
    row = ttk.Frame(frm)
    row.pack(fill="x", pady=(2, 0))
    ttk.Entry(row, textvariable=session_var, font=("Segoe UI", 10)).pack(
        side="left", fill="x", expand=True)
    ttk.Button(row, text="Выбрать…", command=pick_folder,
               style="Outline.TButton").pack(side="left", padx=(8, 0))

    # ── Speaker map section ───────────────────────────────────────────────

    speaker_lf = ttk.LabelFrame(frm, text="Игроки (speaker map)")
    speaker_lf.pack(fill="x", pady=(10, 0))

    speaker_btn_row = ttk.Frame(speaker_lf)
    speaker_btn_row.pack(fill="x", padx=8, pady=(4, 2))
    ttk.Button(speaker_btn_row, text="Загрузить…", command=load_map_file,
               style="Outline.TButton").pack(side="left")
    ttk.Button(speaker_btn_row, text="Сохранить", command=save_map,
               style="Link.TButton").pack(side="left", padx=(6, 0))
    ttk.Label(speaker_btn_row, textvariable=speaker_status_var,
              style="Dim.TLabel").pack(side="left", padx=10)

    hdr = ttk.Frame(speaker_lf)
    hdr.pack(fill="x", padx=8)
    ttk.Label(hdr, text="Discord ник", width=20, anchor="w", style="Header.TLabel").pack(side="left")
    ttk.Label(hdr, text="Игрок", width=15, anchor="w", style="Header.TLabel").pack(side="left", padx=4)
    ttk.Label(hdr, text="Персонаж", width=15, anchor="w", style="Header.TLabel").pack(side="left", padx=4)
    ttk.Label(hdr, text="Роль", width=6, anchor="w", style="Header.TLabel").pack(side="left", padx=4)

    speaker_table = ttk.Frame(speaker_lf)
    speaker_table.pack(fill="x", padx=8, pady=(0, 6))

    # ── GPU status ────────────────────────────────────────────────────────

    gpu_lf = ttk.LabelFrame(frm, text="Устройство (GPU / CPU)")
    gpu_lf.pack(fill="x", pady=(10, 0))

    # Decide style for GPU bar
    gpu_status_text, _gpu_color = _format_gpu_status(gpu_info)
    if gpu_info["error"]:
        _gpu_style = "GpuErr.TLabel"
    elif not gpu_info["cuda_available"]:
        _gpu_style = "GpuWarn.TLabel"
    else:
        _gpu_style = "GpuOk.TLabel"

    gpu_label = ttk.Label(gpu_lf, text=gpu_status_text, style=_gpu_style, anchor="w")
    gpu_label.pack(fill="x", padx=8, pady=(6, 2))

    device_row = ttk.Frame(gpu_lf)
    device_row.pack(fill="x", padx=8, pady=(0, 6))
    ttk.Label(device_row, text="device:").pack(side="left")
    ttk.Combobox(device_row, textvariable=device_var, values=["cuda", "cpu"],
                 width=8, state="readonly").pack(side="left", padx=(4, 0))

    def _recheck_gpu() -> None:
        fresh = _detect_gpu()
        txt_val, _col = _format_gpu_status(fresh)
        if fresh["error"]:
            s = "GpuErr.TLabel"
        elif not fresh["cuda_available"]:
            s = "GpuWarn.TLabel"
        else:
            s = "GpuOk.TLabel"
        gpu_label.config(text=txt_val, style=s)
        device_var.set("cuda" if fresh["cuda_available"] else "cpu")

    ttk.Button(device_row, text="Перепроверить", command=_recheck_gpu,
               style="Link.TButton").pack(side="left", padx=10)

    # ── Options ───────────────────────────────────────────────────────────

    ttk.Checkbutton(frm, text="Только склейка (json уже есть)",
                    variable=merge_only_var).pack(anchor="w", pady=(10, 0))

    # ── FVTT Chat Log section ──────────────────────────────────────────
    chat_lf = ttk.LabelFrame(frm, text="Лог из чата (FVTT)")
    chat_lf.pack(fill="x", pady=(8, 0))

    chat_row1 = ttk.Frame(chat_lf)
    chat_row1.pack(fill="x", padx=6, pady=(4, 0))
    ttk.Checkbutton(chat_row1, text="Добавить лог из чата",
                    variable=chat_log_var).pack(side="left")

    chat_row2 = ttk.Frame(chat_lf)
    chat_row2.pack(fill="x", padx=6, pady=(2, 0))
    chat_path_entry = ttk.Entry(chat_row2, textvariable=chat_log_path_var, state="readonly")
    chat_path_entry.pack(side="left", fill="x", expand=True)

    def pick_chat_log() -> None:
        f = filedialog.askopenfilename(
            title="Выберите лог чата FVTT",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if f:
            chat_log_path_var.set(f)
            chat_log_var.set(True)

    ttk.Button(chat_row2, text="Выбрать…", command=pick_chat_log,
               style="Outline.TButton").pack(side="left", padx=(6, 0))

    chat_row3 = ttk.Frame(chat_lf)
    chat_row3.pack(fill="x", padx=6, pady=(2, 6))
    ttk.Label(chat_row3, text="Часовой пояс:").pack(side="left")
    tz_values = [f"UTC{h:+d}" for h in range(-12, 15)]
    tz_combo = ttk.Combobox(chat_row3, textvariable=chat_tz_var,
                            values=["auto"] + tz_values, width=10, state="readonly")
    tz_combo.pack(side="left", padx=(6, 0))

    model_row = ttk.Frame(frm)
    model_row.pack(fill="x", pady=(6, 0))
    ttk.Label(model_row, text="Whisper model:").pack(side="left")
    ttk.Combobox(model_row, textvariable=model_var, values=["large-v2", "large-v3"],
                 width=12, state="readonly").pack(side="left", padx=(6, 0))
    ttk.Label(model_row, text="compute:").pack(side="left", padx=(14, 4))
    ttk.Combobox(model_row, textvariable=compute_type_var,
                 values=["float16", "float32"], width=10, state="readonly").pack(side="left")
    ttk.Label(model_row, text="beam:").pack(side="left", padx=(14, 4))
    ttk.Combobox(model_row, textvariable=beam_size_var,
                 values=["5", "10", "20"], width=6, state="readonly").pack(side="left")

    chunk_row = ttk.Frame(frm)
    chunk_row.pack(fill="x", pady=(6, 0))
    ttk.Checkbutton(chunk_row, text="Нарезать на чанки", variable=chunk_var).pack(side="left")
    ttk.Label(chunk_row, text="chunk chars:").pack(side="left", padx=(14, 4))
    ttk.Entry(chunk_row, textvariable=chunk_chars_var, width=8).pack(side="left")
    ttk.Label(chunk_row, text="overlap:").pack(side="left", padx=(14, 4))
    ttk.Entry(chunk_row, textvariable=chunk_overlap_var, width=6).pack(side="left")

    # ── Action button + progress ─────────────────────────────────────────

    ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=(10, 8))

    btn_start = ttk.Button(frm, text="▶ Запустить", command=start, style="Accent.TButton")
    btn_start.pack(anchor="w")

    # Progress bar + status label side by side
    progress_row = ttk.Frame(frm)
    progress_row.pack(fill="x", pady=(6, 0))

    progress_var = tk.DoubleVar(value=0)
    progress_bar = ttk.Progressbar(
        progress_row, variable=progress_var, maximum=100,
        style="pointed.Horizontal.TProgressbar")
    progress_bar.pack(fill="x", expand=True)

    # ── Log output (terminal-style) ─────────────────────────────────────

    ttk.Label(root, text="  Лог", style="Dim.TLabel",
              font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(6, 0))
    log_frame = tk.Frame(root, bg="#11111b", bd=1, relief="flat",
                          highlightbackground="#45475a", highlightthickness=1)
    log_frame.pack(fill="both", expand=True, padx=14, pady=(6, 0))

    txt = tk.Text(log_frame, bg="#11111b", fg="#a6adc8",
                  insertbackground="#a6adc8", selectbackground=ACCENT,
                  font=("Consolas", 9), borderwidth=0, padx=8, pady=6,
                  wrap="word")
    txt.pack(fill="both", expand=True)

    # Mousewheel scrolling (no visible scrollbar — cleaner look)
    def _on_mousewheel(event):
        txt.yview_scroll(int(-1 * (event.delta / 120)), "units")
    txt.bind("<MouseWheel>", _on_mousewheel)

    # ── Status bar (bottom) ──────────────────────────────────────────────

    status_var.set("Готов к запуску")
    status_bar = ttk.Label(root, textvariable=status_var, style="StatusBar.TLabel",
                            anchor="w")
    status_bar.pack(fill="x", side="bottom")

    # Start the log queue polling
    _poll_log_queue()

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
