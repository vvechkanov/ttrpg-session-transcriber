"""GUI entry point (tkinter). Depends only on core."""

from __future__ import annotations

import json
import logging
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

# Tkinter imports are lazy inside gui_main to keep headless CLI working.

from core import PipelineParams, run as core_run
from core.backend_installers import (
    BackendId,
    install_backend,
    is_backend_installed,
)
from core.speaker_map import (
    SPEAKER_MAP_FILENAME,
    load_speaker_map as core_load_speaker_map,
    load_speaker_map_raw,
    migrate_legacy_speaker_map,
    save_speaker_map_raw,
)

EXCLUDE_AUDIO_PREFIXES = ("craig",)


def _scan_audio_files(session_dir: Path, pattern: str = "*.flac") -> list[str]:
    """Return sorted list of audio file stems, excluding craig tracks."""
    return sorted(
        p.stem
        for p in session_dir.glob(pattern)
        if not any(p.stem.lower() == x or p.stem.lower().startswith(x + "-") for x in EXCLUDE_AUDIO_PREFIXES)
    )


class _QueueLogHandler(logging.Handler):
    """Piping logging.LogRecord into the GUI log widget queue."""

    def __init__(self, q: "queue.Queue[str]") -> None:
        super().__init__(level=logging.INFO)
        self.queue = q
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put(self.format(record))
        except Exception:
            pass


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
    chunk_var = tk.BooleanVar(value=True)
    chunk_chars_var = tk.StringVar(value="40000")
    chunk_overlap_var = tk.StringVar(value="0.20")
    model_var = tk.StringVar(value="large-v3")
    compute_type_var = tk.StringVar(value="float16")
    beam_size_var = tk.StringVar(value="10")
    # Speech backend picker — GUI по умолчанию faster-whisper; "gigaam" тоже
    # доступен, но требует установленных моделей (проверяется в start()).
    speech_backend_var = tk.StringVar(value="faster-whisper")

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
        # One-shot migration: copy legacy <repo_root>/speaker_map.json into
        # the session folder on first load. Legacy file is left intact.
        migrated = migrate_legacy_speaker_map(session_dir)
        if migrated is not None:
            log(f"Мигрирован legacy speaker_map → {migrated}")
        smap = load_speaker_map_raw(session_dir)
        session_map_path = session_dir / SPEAKER_MAP_FILENAME
        if session_map_path.exists():
            speaker_status_var.set("Загружен из папки сессии")
        elif smap:
            # No file in session_dir but loader returned data → it came from
            # the legacy project-root fallback inside load_speaker_map_raw.
            speaker_status_var.set("Загружен из папки проекта (legacy)")
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
                    from core.fvtt_helpers import detect_fvtt_tz_offset
                    tz = detect_fvtt_tz_offset(fvtt_logs[0], info_path)
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
        if not f:
            return
        # User picked an arbitrary path → read it directly (not via the
        # session-aware core helper). The picked file is treated as a
        # one-off import; saving will still go to session_dir.
        try:
            smap = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            smap = {}
        if not isinstance(smap, dict) or not smap:
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
        session_dir_str = session_var.get().strip()
        if not session_dir_str:
            messagebox.showwarning(
                "Нет папки сессии",
                "Сначала выберите папку сессии — speaker_map сохраняется туда.",
            )
            return
        session_dir = Path(session_dir_str).expanduser().resolve()
        if not session_dir.is_dir():
            messagebox.showerror("Ошибка", f"Папка не найдена: {session_dir}")
            return
        # Merge with existing data in session_dir to preserve entries for
        # absent players. Canonical location is <session_dir>/speaker_map.json.
        existing = load_speaker_map_raw(session_dir)
        existing.update(data)
        save_path = save_speaker_map_raw(session_dir, existing)
        speaker_status_var.set(f"Сохранён: {save_path}")

    # ── Lazy backend install modal ────────────────────────────────────────

    def _show_install_modal(backend_id: BackendId) -> bool:
        """Показать модальное окно установки модели.

        Возвращает True если установка прошла успешно, False — при ошибке
        или если пользователь закрыл окно. Блокирует основное окно пока
        установка идёт. См. spec gigaam-v2.md §8.
        """
        modal = tk.Toplevel(root)
        modal.title("Установка модели")
        modal.geometry("480x220")
        modal.transient(root)
        modal.grab_set()
        modal.resizable(False, False)

        tk.Label(
            modal,
            text=f"Установка {backend_id.value}",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=16, pady=(16, 6))

        status_lbl = tk.Label(
            modal,
            text="Подготовка...",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=440,
        )
        status_lbl.pack(fill="x", padx=16, pady=(0, 8))

        pb_var = tk.DoubleVar(value=0.0)
        pb = ttk.Progressbar(
            modal,
            variable=pb_var,
            maximum=100,
            length=440,
        )
        pb.pack(padx=16, pady=(0, 8))

        result: dict[str, bool] = {"ok": False}
        progress_q: queue.Queue = queue.Queue()

        def _worker_install() -> None:
            try:
                install_backend(
                    backend_id,
                    progress=lambda f, m: progress_q.put((f, m)),
                )
                result["ok"] = True
            except Exception as exc:  # noqa: BLE001 — surface to user
                progress_q.put((-1.0, f"Ошибка: {exc}"))
            finally:
                progress_q.put(None)  # sentinel

        threading.Thread(target=_worker_install, daemon=True).start()

        def _poll_install() -> None:
            try:
                while True:
                    item = progress_q.get_nowait()
                    if item is None:
                        modal.destroy()
                        return
                    fraction, msg = item
                    if fraction >= 0:
                        pb_var.set(fraction * 100)
                    status_lbl.config(text=msg)
            except queue.Empty:
                pass
            modal.after(100, _poll_install)

        modal.after(100, _poll_install)
        root.wait_window(modal)
        return result["ok"]

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

        # Auto-save speaker map if any fields are filled. Canonical location
        # is <session_dir>/speaker_map.json (same place CLI reads from).
        speaker_data = _collect_speaker_data()
        if speaker_data:
            existing = load_speaker_map_raw(session_dir)
            existing.update(speaker_data)
            save_path = save_speaker_map_raw(session_dir, existing)
            log(f"Speaker map сохранён: {save_path}")

        # Snapshot all UI values before spawning thread (tkinter is not thread-safe)
        params = {
            "session_dir": session_dir,
            "speech_backend": speech_backend_var.get().strip() or "faster-whisper",
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

        # Lazy-install gate: если выбран backend который требует моделей
        # и они не установлены — показать модалку перед запуском worker-а.
        if params["speech_backend"] == "gigaam":
            if not is_backend_installed(BackendId.GIGAAM_RNNT_FP32):
                if not _show_install_modal(BackendId.GIGAAM_RNNT_FP32):
                    log("Установка GigaAM отменена или не удалась — запуск отменён.")
                    return

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
        """Actual pipeline logic (called from worker thread).

        Calls core.run() with a logging handler piping core.*/sources.*/
        mergers.*/renderers.* records into the GUI log widget queue.
        """
        session_dir = p["session_dir"]

        # Chat log auto-detection happens inside core.pipeline.run() via
        # core.discovery.find_fvtt_chat_log. GUI's chat_log_enabled/
        # chat_log_path/chat_tz_offset are ignored in P2.7 — log an info
        # line if the user set them so they know why.
        if p.get("chat_log_enabled"):
            log("ℹ️ Chat log auto-detected by core.discovery — GUI tz override ignored in P2.7")

        params = PipelineParams(
            speech_backend=p.get("speech_backend", "faster-whisper"),
            model=p["model"],
            device=p["device"],
            compute_type=p["compute_type"],
            language="ru",
            beam_size=p["beam_size"],
            speaker_map=core_load_speaker_map(session_dir) or None,
        )

        _set_status("Обработка сессии…")
        log(f"\n{'═' * 50}")
        log(f"== Устройство: {params.device.upper()}  |  model: {params.model}"
            f"  |  compute: {params.compute_type}  |  beam: {params.beam_size}")
        log(f"{'═' * 50}")

        # Install logging handler for real-time log streaming from core.
        handler = _QueueLogHandler(_log_queue)
        core_logger = logging.getLogger("core")
        sources_logger = logging.getLogger("sources")
        mergers_logger = logging.getLogger("mergers")
        renderers_logger = logging.getLogger("renderers")
        all_loggers = (core_logger, sources_logger, mergers_logger, renderers_logger)
        prior_levels: dict[logging.Logger, int] = {}
        for lg in all_loggers:
            prior_levels[lg] = lg.level
            lg.setLevel(logging.INFO)
            lg.addHandler(handler)

        t_pipeline = time.time()
        try:
            core_run(session_dir, params)
        finally:
            for lg in all_loggers:
                lg.removeHandler(handler)
                lg.setLevel(prior_levels[lg])
        log(f"   ✓ core.run() готов за {_fmt_elapsed(time.time() - t_pipeline)}")

        # ── Chunk post-step (unchanged from legacy) ───────────────
        if p.get("do_chunk"):
            chunk_script = (
                Path(__file__).resolve().parents[1] / "scripts" / "chunk_text.py"
            )
            merged_txt = session_dir / "merged.txt"
            if not merged_txt.exists():
                raise RuntimeError("После склейки не найден merged.txt")
            if not chunk_script.exists():
                log(f"⚠️ chunk_text.py not found at {chunk_script}, пропускаю нарезку")
                return

            _set_status("Нарезка на чанки…")
            log("\n== Нарезка на чанки")
            t_chunk = time.time()
            chunk_cmd = [
                sys.executable,
                str(chunk_script),
                str(merged_txt),
                "--chunk_chars",
                str(p["chunk_chars"]),
                "--overlap",
                str(p["chunk_overlap"]),
            ]
            run_and_stream(chunk_cmd, cwd=session_dir)
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
