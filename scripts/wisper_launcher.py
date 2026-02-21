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
    """
    root = _project_root()

    parts: list[str] = []

    venv_scripts = root / "venv" / "Scripts"
    if venv_scripts.is_dir():
        parts.append(str(venv_scripts))

    ffmpeg_bin = root / "tools" / "ffmpeg" / "bin"
    if ffmpeg_bin.is_dir():
        parts.append(str(ffmpeg_bin))

    if parts:
        os.environ["PATH"] = ";".join(parts + [os.environ.get("PATH", "")])


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
    root.geometry("720x420")

    session_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="Выберите папку сессии (где лежат *.flac и speaker_map.json).")
    merge_only_var = tk.BooleanVar(value=False)
    chunk_var = tk.BooleanVar(value=True)
    chunk_chars_var = tk.StringVar(value="40000")
    chunk_overlap_var = tk.StringVar(value="0.20")
    model_var = tk.StringVar(value="large-v3")
    compute_type_var = tk.StringVar(value="float16")
    beam_size_var = tk.StringVar(value="10")

    def log(msg: str) -> None:
        txt.insert("end", msg + "\n")
        txt.see("end")
        root.update_idletasks()

    def run_and_log(cmd: list[str], *, cwd: Path | None = None) -> None:
        # Capture output so we can show real errors instead of a generic "exit status 1".
        log(">> " + " ".join(cmd))
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
        )
        if p.stdout:
            log(p.stdout.rstrip())
        if p.stderr:
            log(p.stderr.rstrip())
        if p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, cmd, output=p.stdout, stderr=p.stderr)

    def pick_folder() -> None:
        d = filedialog.askdirectory(title="Выберите папку сессии")
        if d:
            session_var.set(d)

    def start() -> None:
        session_dir = Path(session_var.get()).expanduser().resolve()
        if not session_dir.exists():
            messagebox.showerror("Ошибка", "Папка не найдена.")
            return

        output_dir = session_dir
        merge_script = (Path(__file__).resolve().parent / "merge_whisperx.py").resolve()

        try:
            # If merge-only OR json already exist, skip whisperx.
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

                # Defaults tuned for your setup; edit here if needed.
                model = model_var.get().strip() or "large-v2"
                language = "ru"
                device = "cuda"
                compute_type = compute_type_var.get().strip() or "float16"
                vad_method = "silero"
                try:
                    beam_size = int(beam_size_var.get().strip())
                except Exception:
                    beam_size = 5
                if beam_size <= 0:
                    beam_size = 5

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

    frm = tk.Frame(root)
    frm.pack(fill="x", padx=10, pady=10)

    tk.Label(frm, text="Папка сессии:").pack(anchor="w")
    row = tk.Frame(frm)
    row.pack(fill="x")
    tk.Entry(row, textvariable=session_var).pack(side="left", fill="x", expand=True)
    tk.Button(row, text="Выбрать…", command=pick_folder).pack(side="left", padx=8)

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

    txt = tk.Text(root, height=12)
    txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
