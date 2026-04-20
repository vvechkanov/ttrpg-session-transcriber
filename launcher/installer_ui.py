"""Installer UI — tkinter window showing installation progress.

The first-run installer has exactly two stages:

    1. **ffmpeg**  — download and extract ffmpeg to
       ``DATA_DIR/tools/ffmpeg``.
    2. **runtime** — download ``session-transcriber.zip`` from the
       matching GitHub Release tag and unpack it into
       ``DATA_DIR/session-transcriber/``. That directory contains
       ``session-transcriber.exe`` (the PySide6 shell) which is what
       the bootstrap EXE Popen-s after installation.

Speech-recognition models are **not** installed here — the user is
asked about them lazily, only when they actually add a speech parser
to a session from inside the shell. Install / uninstall of individual
backends is handled through :mod:`core.backend_installers` and driven
from the Models screen in the QML shell. This keeps first-run free of
multi-GB questions and lets chat-only users skip the ASR download
entirely.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import ttk
from typing import Callable

try:
    from launcher.install_logic import (
        STEP_WEIGHTS,
        detect_gpu,
        download_ffmpeg,
        download_runtime_zip,
    )
except ImportError:  # running from extracted folder
    from install_logic import (  # type: ignore[no-redef]
        STEP_WEIGHTS,
        detect_gpu,
        download_ffmpeg,
        download_runtime_zip,
    )

# ---------------------------------------------------------------------------
# Theme (matches wisper_launcher.py)
# ---------------------------------------------------------------------------
BG = "#1e1e2e"
BG2 = "#2a2a3c"
FG = "#cdd6f4"
FG_DIM = "#6c7086"
ACCENT = "#40b87c"
WARN = "#f9a825"
ERR = "#f44336"
INPUT_BG = "#313244"
INPUT_FG = "#cdd6f4"

# Visible progress stages — order matches the worker flow below. Models
# are installed lazily from the shell, not here.
STEPS: list[tuple[str, str]] = [
    ("ffmpeg", "Загрузка ffmpeg"),
    ("runtime", "Загрузка приложения"),
]


class InstallerWindow:
    """tkinter window that drives a 2-stage install + progress bar.

    Args:
        data_dir: ``%APPDATA%/ttrpg-transcriber``; the installer
            writes ``tools/ffmpeg/`` and ``session-transcriber/``
            under here. Model directories appear later, when the
            shell lazily installs an ASR backend.
        version: application version string — used to build the
            GitHub Release URL for the runtime zip (tag ``v{version}``).
        on_complete: called on the main thread after the runtime zip
            has been unpacked successfully. The bootstrap passes a
            callback that writes the ``.installed`` sentinel and then
            ``Popen``-s the runtime EXE.
    """

    def __init__(
        self,
        data_dir: Path,
        version: str,
        on_complete: Callable[[], None],
    ):
        self.data_dir = data_dir
        self.version = version
        self.on_complete = on_complete

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._step_progress: dict[str, float] = {s[0]: 0.0 for s in STEPS}
        self._current_step = ""
        self._gpu_mode = "cpu"
        self._error: str | None = None

        self._build_ui()

    # ─────────────────────────────────── UI ──────────────────────────────

    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("WhisperX Transcriber — Установка")
        self.root.geometry("680x560")
        self.root.minsize(560, 480)
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        # Prevent close during installation
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, borderwidth=0)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TFrame", background=BG)
        style.configure(
            "Green.Horizontal.TProgressbar",
            troughcolor=INPUT_BG,
            background=ACCENT,
            thickness=20,
        )

        # ── Title ────────────────────────────────────────────────────
        title_frame = tk.Frame(self.root, bg=BG)
        title_frame.pack(fill="x", padx=24, pady=(20, 0))

        tk.Label(
            title_frame,
            text="WhisperX Transcriber",
            font=("Segoe UI", 18, "bold"),
            fg=FG, bg=BG,
        ).pack(anchor="w")

        tk.Label(
            title_frame,
            text=f"Первый запуск — установка v{self.version}",
            font=("Segoe UI", 10),
            fg=FG_DIM, bg=BG,
        ).pack(anchor="w", pady=(2, 0))

        # ── GPU banner ───────────────────────────────────────────────
        self.gpu_frame = tk.Frame(self.root, bg="#1a3d2a", padx=12, pady=8)
        self.gpu_frame.pack(fill="x", padx=24, pady=(16, 0))

        self.gpu_label = tk.Label(
            self.gpu_frame,
            text="Определение GPU...",
            font=("Segoe UI", 9, "bold"),
            fg=ACCENT, bg="#1a3d2a",
        )
        self.gpu_label.pack(anchor="w")

        # ── Steps ────────────────────────────────────────────────────
        steps_frame = tk.Frame(self.root, bg=BG)
        steps_frame.pack(fill="x", padx=24, pady=(16, 0))

        self._step_labels: dict[str, tk.Label] = {}
        self._step_status: dict[str, tk.Label] = {}

        for step_id, step_name in STEPS:
            row = tk.Frame(steps_frame, bg=BG)
            row.pack(fill="x", pady=2)

            marker = tk.Label(
                row, text="○", font=("Segoe UI", 11),
                fg=FG_DIM, bg=BG, width=2,
            )
            marker.pack(side="left")
            self._step_labels[step_id] = marker

            tk.Label(
                row, text=step_name, font=("Segoe UI", 10),
                fg=FG, bg=BG,
            ).pack(side="left", padx=(4, 0))

            status = tk.Label(
                row, text="", font=("Segoe UI", 9),
                fg=FG_DIM, bg=BG,
            )
            status.pack(side="right")
            self._step_status[step_id] = status

        # ── Models hint (install is deferred to the shell) ──────────
        hint_frame = tk.Frame(self.root, bg=BG)
        hint_frame.pack(fill="x", padx=24, pady=(8, 0))
        tk.Label(
            hint_frame,
            text=(
                "Модель распознавания речи будет предложена к установке "
                "позже — когда вы добавите парсер в сессию."
            ),
            font=("Segoe UI", 9),
            fg=FG_DIM, bg=BG,
            wraplength=600,
            justify="left",
        ).pack(anchor="w")

        # ── Log area ─────────────────────────────────────────────────
        log_frame = tk.Frame(self.root, bg=INPUT_BG, padx=1, pady=1)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(16, 0))

        self.log_text = tk.Text(
            log_frame,
            bg=INPUT_BG, fg=INPUT_FG,
            font=("Consolas", 9),
            wrap="word",
            state="disabled",
            bd=0, padx=8, pady=8,
            highlightthickness=0,
        )
        self.log_text.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(fill="y", side="right")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # ── Overall progress ─────────────────────────────────────────
        bottom_frame = tk.Frame(self.root, bg=BG)
        bottom_frame.pack(fill="x", padx=24, pady=(12, 20))

        self.progress_label = tk.Label(
            bottom_frame,
            text="Общий прогресс: 0%",
            font=("Segoe UI", 10),
            fg=FG, bg=BG,
        )
        self.progress_label.pack(anchor="w")

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            bottom_frame,
            variable=self.progress_var,
            maximum=100,
            style="Green.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill="x", pady=(6, 0))

        # ── Retry button (hidden initially) ──────────────────────────
        self.retry_btn = tk.Button(
            bottom_frame,
            text="Повторить",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT, fg="#fff",
            activebackground="#36a06a",
            bd=0, padx=16, pady=6,
            command=self._start_install,
        )
        # Not packed yet — shown only on error

    # ────────────────────────────── lifecycle ───────────────────────────

    def run(self) -> None:
        """Show the window and start installation."""
        self._start_install()
        self._poll_log()
        self.root.mainloop()

    def _start_install(self) -> None:
        """(Re)start the installation in a background thread."""
        self.retry_btn.pack_forget()
        self._error = None
        for step_id, _ in STEPS:
            self._step_progress[step_id] = 0.0
            self._step_labels[step_id].config(text="○", fg=FG_DIM)
            self._step_status[step_id].config(text="")
        self._update_overall_progress()

        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self) -> None:
        """Run all installation steps in a background thread."""
        try:
            # Detect GPU (informational only — no torch install anymore)
            self._gpu_mode = detect_gpu(self._log)
            self.root.after(0, self._update_gpu_banner)

            ffmpeg_dir = self.data_dir / "tools" / "ffmpeg"

            # Step 1: ffmpeg
            self._begin_step("ffmpeg")
            download_ffmpeg(
                ffmpeg_dir, self._log, self._step_progress_fn("ffmpeg")
            )
            self._complete_step("ffmpeg")

            # Step 2: PySide6 runtime zip from GitHub Release.
            # Models are NOT installed here — the shell installs each
            # backend lazily via :mod:`core.backend_installers` when
            # the user picks it on the Models screen.
            self._begin_step("runtime")
            download_runtime_zip(
                self.data_dir,
                self.version,
                self._log,
                self._step_progress_fn("runtime"),
            )
            self._complete_step("runtime")

            self._log("")
            self._log("=" * 50)
            self._log("  Установка завершена!")
            self._log("=" * 50)

            self.root.after(500, self._on_install_complete)

        except Exception as e:  # noqa: BLE001 — UI boundary
            self._error = str(e)
            self._log(f"\nОШИБКА: {e}")
            self._log(traceback.format_exc())
            self.root.after(0, self._on_install_error)

    # ─────────────────────────── progress helpers ──────────────────────

    def _begin_step(self, step_id: str) -> None:
        self._current_step = step_id
        self._step_progress[step_id] = 0.0
        self.root.after(0, lambda: (
            self._step_labels[step_id].config(text="▶", fg=ACCENT),
            self._step_status[step_id].config(text="0%", fg=ACCENT),
        ))

    def _complete_step(self, step_id: str) -> None:
        self._step_progress[step_id] = 100.0
        self.root.after(0, lambda: (
            self._step_labels[step_id].config(text="✓", fg=ACCENT),
            self._step_status[step_id].config(text="✓", fg=ACCENT),
        ))
        self._update_overall_progress()

    def _step_progress_fn(self, step_id: str) -> Callable[[float], None]:
        """Return a progress callback for a specific step."""
        def update(percent: float) -> None:
            self._step_progress[step_id] = min(percent, 100.0)
            self.root.after(0, lambda: (
                self._step_status[step_id].config(
                    text=f"{int(percent)}%", fg=ACCENT
                ),
            ))
            self._update_overall_progress()
        return update

    def _update_overall_progress(self) -> None:
        total = sum(
            self._step_progress[s] * STEP_WEIGHTS[s] / 100.0
            for s in STEP_WEIGHTS
        )
        overall = total / sum(STEP_WEIGHTS.values()) * 100
        self.root.after(0, lambda: (
            self.progress_var.set(overall),
            self.progress_label.config(text=f"Общий прогресс: {int(overall)}%"),
        ))

    def _update_gpu_banner(self) -> None:
        if self._gpu_mode == "cuda":
            self.gpu_frame.config(bg="#1a3d2a")
            self.gpu_label.config(
                text="GPU обнаружена — runtime будет использовать CUDA",
                fg=ACCENT, bg="#1a3d2a",
            )
        else:
            self.gpu_frame.config(bg="#3d3a1a")
            self.gpu_label.config(
                text="GPU не обнаружена — runtime будет использовать CPU (медленнее)",
                fg=WARN, bg="#3d3a1a",
            )

    # ────────────────────────────── logging ────────────────────────────

    def _log(self, msg: str) -> None:
        """Thread-safe log message."""
        self._log_queue.put(msg)

    def _poll_log(self) -> None:
        """Drain log queue into the text widget (runs on main thread)."""
        while True:
            try:
                msg = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(100, self._poll_log)

    # ────────────────────────────── finish ─────────────────────────────

    def _on_install_complete(self) -> None:
        """Called on the main thread after successful installation."""
        self.progress_label.config(
            text="Установка завершена! Запуск приложения...",
            fg=ACCENT,
        )
        self.root.after(1500, self._finish)

    def _on_install_error(self) -> None:
        """Called on the main thread after a failed installation."""
        self.progress_label.config(text="Ошибка установки", fg=ERR)
        if self._current_step:
            self._step_labels[self._current_step].config(text="✗", fg=ERR)
            self._step_status[self._current_step].config(text="Ошибка", fg=ERR)
        self.retry_btn.pack(pady=(10, 0))

    def _finish(self) -> None:
        """Destroy installer window and call completion callback."""
        self.root.destroy()
        self.on_complete()

    def _on_close(self) -> None:
        """Handle window close — block during active installation."""
        if self._current_step and not self._error:
            return
        self.root.destroy()
