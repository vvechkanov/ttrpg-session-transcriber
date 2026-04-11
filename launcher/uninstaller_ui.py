"""Uninstaller UI — tkinter confirmation + progress window.

Shown when the bootstrap EXE is launched with ``--uninstall`` (either
manually or via Add/Remove Programs). Displays:

    * The data directory that will be wiped and its approximate size.
    * A log area with step-by-step progress.
    * A progress bar.
    * Cancel / "Удалить" buttons.

Runs the actual deletion on a background thread via
:func:`launcher.uninstall_logic.uninstall_everything`. All theming
matches :mod:`launcher.installer_ui`.
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
    from launcher.uninstall_logic import (
        _dir_size_kb,
        uninstall_everything,
    )
except ImportError:  # frozen EXE
    from uninstall_logic import (  # type: ignore[no-redef]
        _dir_size_kb,
        uninstall_everything,
    )


# ---------------------------------------------------------------------------
# Theme (matches installer_ui.py)
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


class UninstallerWindow:
    """tkinter window that drives the uninstall flow.

    Args:
        data_dir: ``%APPDATA%/ttrpg-transcriber``.
        skip_self: optional path that must NOT be deleted — typically
            the running ``uninstall.exe`` copy inside ``data_dir``.
            Passed straight through to
            :func:`uninstall_logic.uninstall_everything`.
        on_complete: callback invoked on the main thread after a
            successful uninstall. Used by the bootstrap to schedule
            self-deletion via the ``--from-temp`` relocation trick.
    """

    def __init__(
        self,
        data_dir: Path,
        skip_self: Path | None,
        on_complete: Callable[[], None],
    ) -> None:
        self.data_dir = data_dir
        self.skip_self = skip_self
        self.on_complete = on_complete

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._error: str | None = None
        self._running = False
        self._done = False

        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("WhisperX Transcriber — Удаление")
        self.root.geometry("620x460")
        self.root.minsize(520, 400)
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, borderwidth=0)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TFrame", background=BG)
        style.configure(
            "Red.Horizontal.TProgressbar",
            troughcolor=INPUT_BG,
            background=ERR,
            thickness=18,
        )

        # Title
        title_frame = tk.Frame(self.root, bg=BG)
        title_frame.pack(fill="x", padx=24, pady=(20, 0))

        tk.Label(
            title_frame,
            text="Удаление WhisperX Transcriber",
            font=("Segoe UI", 16, "bold"),
            fg=FG, bg=BG,
        ).pack(anchor="w")

        size_kb = _dir_size_kb(self.data_dir)
        size_mb = size_kb / 1024
        tk.Label(
            title_frame,
            text=f"Будут удалены все данные приложения (~{size_mb:.0f} MB):",
            font=("Segoe UI", 10),
            fg=FG_DIM, bg=BG,
        ).pack(anchor="w", pady=(4, 0))

        tk.Label(
            title_frame,
            text=str(self.data_dir),
            font=("Consolas", 9),
            fg=WARN, bg=BG,
        ).pack(anchor="w", pady=(2, 0))

        # Warning banner
        warn_frame = tk.Frame(self.root, bg="#3d3a1a", padx=12, pady=8)
        warn_frame.pack(fill="x", padx=24, pady=(12, 0))

        tk.Label(
            warn_frame,
            text=(
                "Это действие необратимо. Будут удалены модели ASR, "
                "ffmpeg, runtime-приложение и все настройки. "
                "Транскрипты и проекты в других папках НЕ затрагиваются."
            ),
            font=("Segoe UI", 9),
            fg=WARN, bg="#3d3a1a",
            wraplength=540, justify="left",
        ).pack(anchor="w")

        # Log area
        log_frame = tk.Frame(self.root, bg=INPUT_BG, padx=1, pady=1)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(12, 0))

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

        # Progress
        bottom_frame = tk.Frame(self.root, bg=BG)
        bottom_frame.pack(fill="x", padx=24, pady=(10, 14))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            bottom_frame,
            variable=self.progress_var,
            maximum=100,
            style="Red.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill="x", pady=(0, 8))

        # Buttons
        btn_frame = tk.Frame(bottom_frame, bg=BG)
        btn_frame.pack(fill="x")

        self.cancel_btn = tk.Button(
            btn_frame,
            text="Отмена",
            font=("Segoe UI", 10),
            bg=BG2, fg=FG,
            activebackground="#3a3a4e",
            bd=0, padx=16, pady=6,
            command=self._on_cancel,
        )
        self.cancel_btn.pack(side="right", padx=(8, 0))

        self.delete_btn = tk.Button(
            btn_frame,
            text="Удалить",
            font=("Segoe UI", 10, "bold"),
            bg=ERR, fg="#fff",
            activebackground="#c62828",
            bd=0, padx=16, pady=6,
            command=self._on_delete,
        )
        self.delete_btn.pack(side="right")

    # ── Lifecycle ────────────────────────────────────────────────────

    def run(self) -> None:
        self._poll_log()
        self.root.mainloop()

    def _on_delete(self) -> None:
        if self._running:
            return
        self._running = True
        self.delete_btn.config(state="disabled")
        self.cancel_btn.config(state="disabled")
        threading.Thread(target=self._worker, daemon=True).start()

    def _on_cancel(self) -> None:
        if self._running:
            return
        self.root.destroy()

    def _on_close(self) -> None:
        if self._running:
            return
        self.root.destroy()

    def _worker(self) -> None:
        try:
            uninstall_everything(
                self.data_dir,
                self._log,
                self._progress,
                skip_self=self.skip_self,
            )
            self._done = True
            self.root.after(300, self._on_done)
        except Exception as exc:  # noqa: BLE001 — UI boundary
            self._error = str(exc)
            self._log(f"\nОШИБКА: {exc}")
            self._log(traceback.format_exc())
            self.root.after(0, self._on_error)

    # ── Progress / logging ───────────────────────────────────────────

    def _log(self, msg: str) -> None:
        self._log_queue.put(msg)

    def _poll_log(self) -> None:
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

    def _progress(self, fraction: float) -> None:
        pct = max(0.0, min(1.0, fraction)) * 100
        self.root.after(0, lambda: self.progress_var.set(pct))

    # ── Finish ───────────────────────────────────────────────────────

    def _on_done(self) -> None:
        self.delete_btn.config(text="Готово", state="normal",
                               bg=ACCENT, activebackground="#36a06a",
                               command=self._finish)
        self.cancel_btn.pack_forget()

    def _on_error(self) -> None:
        self.delete_btn.config(text="Закрыть", state="normal",
                               bg=BG2, fg=FG,
                               activebackground="#3a3a4e",
                               command=self.root.destroy)
        self.cancel_btn.pack_forget()

    def _finish(self) -> None:
        self.root.destroy()
        self.on_complete()
