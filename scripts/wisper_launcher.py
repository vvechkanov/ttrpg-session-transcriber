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
import subprocess
import sys
from pathlib import Path

EXCLUDE_AUDIO_PREFIXES = ("craig",)

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
    root.title("WhisperX → merged.txt")
    root.geometry("740x720")

    session_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="Выберите папку сессии (где лежат *.flac).")
    merge_only_var = tk.BooleanVar(value=False)
    chunk_var = tk.BooleanVar(value=True)
    chunk_chars_var = tk.StringVar(value="40000")
    chunk_overlap_var = tk.StringVar(value="0.20")
    model_var = tk.StringVar(value="large-v3")
    compute_type_var = tk.StringVar(value="float16")
    beam_size_var = tk.StringVar(value="10")

    # ── GPU diagnostics ───────────────────────────────────────────────────
    gpu_info = _detect_gpu()
    device_var = tk.StringVar(value="cuda" if gpu_info["cuda_available"] else "cpu")

    speaker_rows: list[dict] = []
    speaker_status_var = tk.StringVar(value="")

    def log(msg: str) -> None:
        txt.insert("end", msg + "\n")
        txt.see("end")
        root.update_idletasks()

    def run_and_log(cmd: list[str], *, cwd: Path | None = None) -> None:
        log(">> " + " ".join(cmd))
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if p.stdout:
            log(p.stdout.rstrip())
        if p.stderr:
            log(p.stderr.rstrip())
        if p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, cmd, output=p.stdout, stderr=p.stderr)

    # ── Speaker map helpers ────────────────────────────────────────────────

    def _rebuild_speaker_table(stems: list[str], smap: dict) -> None:
        speaker_rows.clear()
        for w in speaker_table.winfo_children():
            w.destroy()
        for stem in stems:
            entry = smap.get(stem, {})
            if not isinstance(entry, dict):
                entry = {}
            row_frame = tk.Frame(speaker_table)
            row_frame.pack(fill="x", pady=1)
            player_var = tk.StringVar(value=entry.get("player", ""))
            char_var = tk.StringVar(value=entry.get("character", ""))
            role_var = tk.StringVar(value=entry.get("role", "PC"))
            tk.Label(row_frame, text=stem, width=20, anchor="w").pack(side="left")
            tk.Entry(row_frame, textvariable=player_var, width=15).pack(side="left", padx=4)
            tk.Entry(row_frame, textvariable=char_var, width=15).pack(side="left", padx=4)
            ttk.Combobox(
                row_frame, textvariable=role_var, values=["PC", "GM"], width=4, state="readonly"
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

    def start() -> None:
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

        output_dir = session_dir
        merge_script = (Path(__file__).resolve().parent / "merge_whisperx.py").resolve()

        try:
            jsons = sorted(output_dir.glob("*.json"))
            need_whisperx = not merge_only_var.get() and len(jsons) == 0

            if need_whisperx:
                audio_files = [
                    p
                    for p in sorted(session_dir.glob("*.flac"))
                    if not any(p.stem.lower() == x or p.stem.lower().startswith(x + "-") for x in EXCLUDE_AUDIO_PREFIXES)
                ]
                if not audio_files:
                    messagebox.showerror("Ошибка", "В папке нет *.flac (или всё исключено как craig*).")
                    return

                model = model_var.get().strip() or "large-v2"
                language = "ru"
                device = device_var.get().strip() or "cuda"
                compute_type = compute_type_var.get().strip() or "float16"
                vad_method = "silero"
                try:
                    beam_size = int(beam_size_var.get().strip())
                except Exception:
                    beam_size = 5
                if beam_size <= 0:
                    beam_size = 5

                log(f"\n== Устройство: {device.upper()}"
                    f"  |  model: {model}  |  compute: {compute_type}  |  beam: {beam_size}")

                for audio in audio_files:
                    cmd = [
                        "whisperx",
                        str(audio),
                        "--model",
                        model,
                        "--language",
                        language,
                        "--output_dir",
                        str(output_dir),
                        "--vad_method",
                        vad_method,
                        "--device",
                        device,
                        "--compute_type",
                        compute_type,
                        "--beam_size",
                        str(beam_size),
                    ]
                    run_and_log(cmd, cwd=output_dir)

            # merge
            jsons = sorted(output_dir.glob("*.json"))
            if not jsons:
                messagebox.showerror("Ошибка", "Не найдено ни одного *.json для склейки.")
                return

            cmd = [sys.executable, str(merge_script), *[str(p) for p in jsons]]
            log("\n== Склейка в merged.txt")
            run_and_log(cmd, cwd=output_dir)

            if chunk_var.get():
                chunk_script = (Path(__file__).resolve().parent / "chunk_text.py").resolve()
                merged_txt = output_dir / "merged.txt"
                if not merged_txt.exists():
                    messagebox.showerror("Ошибка", "После склейки не найден merged.txt")
                    return
                try:
                    chunk_chars = int(chunk_chars_var.get().strip())
                except Exception:
                    chunk_chars = 40000
                try:
                    overlap = float(chunk_overlap_var.get().strip().replace(",", "."))
                except Exception:
                    overlap = 0.20

                chunk_cmd = [
                    sys.executable,
                    str(chunk_script),
                    str(merged_txt),
                    "--chunk_chars",
                    str(chunk_chars),
                    "--overlap",
                    str(overlap),
                ]
                log("\n== Нарезка на чанки (chunks\\)")
                run_and_log(chunk_cmd, cwd=output_dir)

            messagebox.showinfo("Готово", f"Сделано: {output_dir}\\merged.txt")
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Ошибка WhisperX", f"Команда завершилась с ошибкой:\n{e}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    # ── Layout ─────────────────────────────────────────────────────────────

    frm = tk.Frame(root)
    frm.pack(fill="x", padx=10, pady=10)

    tk.Label(frm, text="Папка сессии:").pack(anchor="w")
    row = tk.Frame(frm)
    row.pack(fill="x")
    tk.Entry(row, textvariable=session_var).pack(side="left", fill="x", expand=True)
    tk.Button(row, text="Выбрать…", command=pick_folder).pack(side="left", padx=8)

    # ── Speaker map section ────────────────────────────────────────────────

    speaker_lf = tk.LabelFrame(frm, text="Игроки (speaker map)")
    speaker_lf.pack(fill="x", pady=(8, 0))

    speaker_btn_row = tk.Frame(speaker_lf)
    speaker_btn_row.pack(fill="x", padx=4, pady=2)
    tk.Button(speaker_btn_row, text="Загрузить…", command=load_map_file).pack(side="left")
    tk.Button(speaker_btn_row, text="Сохранить", command=save_map).pack(side="left", padx=4)
    tk.Label(speaker_btn_row, textvariable=speaker_status_var, fg="#555").pack(side="left", padx=8)

    hdr = tk.Frame(speaker_lf)
    hdr.pack(fill="x", padx=4)
    tk.Label(hdr, text="Discord ник", width=20, anchor="w", font=("", 8, "bold")).pack(side="left")
    tk.Label(hdr, text="Игрок", width=15, anchor="w", font=("", 8, "bold")).pack(side="left", padx=4)
    tk.Label(hdr, text="Персонаж", width=15, anchor="w", font=("", 8, "bold")).pack(side="left", padx=4)
    tk.Label(hdr, text="Роль", width=6, anchor="w", font=("", 8, "bold")).pack(side="left", padx=4)

    speaker_table = tk.Frame(speaker_lf)
    speaker_table.pack(fill="x", padx=4, pady=(0, 4))

    # ── GPU status ─────────────────────────────────────────────────────────

    gpu_lf = tk.LabelFrame(frm, text="Устройство (GPU / CPU)")
    gpu_lf.pack(fill="x", pady=(8, 0))

    gpu_status_text, gpu_status_color = _format_gpu_status(gpu_info)
    gpu_label = tk.Label(gpu_lf, text=gpu_status_text, fg=gpu_status_color, anchor="w", justify="left")
    gpu_label.pack(fill="x", padx=6, pady=(2, 0))

    device_row = tk.Frame(gpu_lf)
    device_row.pack(fill="x", padx=6, pady=(2, 4))
    tk.Label(device_row, text="device:").pack(side="left")
    ttk.Combobox(
        device_row, textvariable=device_var, values=["cuda", "cpu"], width=8, state="readonly"
    ).pack(side="left", padx=(4, 0))

    def _recheck_gpu() -> None:
        fresh = _detect_gpu()
        txt_val, col = _format_gpu_status(fresh)
        gpu_label.config(text=txt_val, fg=col)
        if fresh["cuda_available"]:
            device_var.set("cuda")
        else:
            device_var.set("cpu")

    tk.Button(device_row, text="Перепроверить", command=_recheck_gpu).pack(side="left", padx=8)

    # ── Options ────────────────────────────────────────────────────────────

    tk.Checkbutton(frm, text="Только склейка (json уже есть)", variable=merge_only_var).pack(anchor="w", pady=(8, 0))

    model_row = tk.Frame(frm)
    model_row.pack(fill="x", pady=(8, 0))
    tk.Label(model_row, text="Whisper model:").pack(side="left")
    ttk.Combobox(model_row, textvariable=model_var, values=["large-v2", "large-v3"], width=14, state="readonly").pack(
        side="left", padx=(8, 0)
    )
    tk.Label(model_row, text="compute:").pack(side="left", padx=(12, 4))
    ttk.Combobox(
        model_row,
        textvariable=compute_type_var,
        values=["float16", "float32"],
        width=10,
        state="readonly",
    ).pack(side="left")
    tk.Label(model_row, text="beam:").pack(side="left", padx=(12, 4))
    ttk.Combobox(
        model_row,
        textvariable=beam_size_var,
        values=["5", "10", "20"],
        width=6,
        state="readonly",
    ).pack(side="left")

    chunk_row = tk.Frame(frm)
    chunk_row.pack(fill="x", pady=(8, 0))
    tk.Checkbutton(chunk_row, text="Нарезать на чанки", variable=chunk_var).pack(side="left")
    tk.Label(chunk_row, text="chunk chars:").pack(side="left", padx=(12, 4))
    tk.Entry(chunk_row, textvariable=chunk_chars_var, width=8).pack(side="left")
    tk.Label(chunk_row, text="overlap:").pack(side="left", padx=(12, 4))
    tk.Entry(chunk_row, textvariable=chunk_overlap_var, width=6).pack(side="left")

    tk.Button(frm, text="Запустить", command=start).pack(anchor="w", pady=(8, 0))
    tk.Label(frm, textvariable=status_var, fg="#555").pack(anchor="w", pady=(8, 0))

    txt = tk.Text(root, height=10)
    txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
