"""
Installer UI — beautiful tkinter window showing installation progress.

Matches the dark theme from wisper_launcher.py.
Runs install_logic functions in a background thread.
"""

from __future__ import annotations

import queue
import threading
import traceback
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import Callable

try:
    from launcher.install_logic import (
        STEP_WEIGHTS, detect_gpu, download_embedded_python, download_ffmpeg,
        extract_embedded_python, install_pip, install_pytorch,
        install_whisperx, repin_pytorch_cuda, verify_installation,
    )
except ImportError:
    from install_logic import (
        STEP_WEIGHTS, detect_gpu, download_embedded_python, download_ffmpeg,
        extract_embedded_python, install_pip, install_pytorch,
        install_whisperx, repin_pytorch_cuda, verify_installation,
    )

# Backend installers (ASR models, e.g. GigaAM). Импортируется после того
# как core.backend_installers добавлен в проект; оборачиваем try/except
# чтобы installer UI мог запуститься в окружении без core-слоя.
try:
    from core.backend_installers import (
        BackendId,
        install_backend,
        list_backends,
    )
    _BACKEND_INSTALLERS_AVAILABLE = True
except ImportError:
    BackendId = None  # type: ignore[assignment,misc]
    install_backend = None  # type: ignore[assignment]
    list_backends = None  # type: ignore[assignment]
    _BACKEND_INSTALLERS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Theme (matches wisper_launcher.py)
# ---------------------------------------------------------------------------
BG       = "#1e1e2e"
BG2      = "#2a2a3c"
FG       = "#cdd6f4"
FG_DIM   = "#6c7086"
ACCENT   = "#40b87c"
WARN     = "#f9a825"
ERR      = "#f44336"
INPUT_BG = "#313244"
INPUT_FG = "#cdd6f4"

# Step definitions
STEPS = [
    ("python",   "Подготовка Python runtime"),
    ("pip",      "Установка pip"),
    ("pytorch",  "Установка PyTorch"),
    ("whisperx", "Установка WhisperX"),
    ("ffmpeg",   "Загрузка ffmpeg"),
    ("models",   "Загрузка моделей"),
]


class InstallerWindow:
    """
    A tkinter window that shows installation progress with:
    - GPU detection banner
    - Per-step status indicators
    - Real-time log output
    - Overall progress bar
    """

    def __init__(
        self,
        data_dir: Path,
        python_zip: Path,
        tkinter_src: Path | None,
        scripts_dir: Path,
        on_complete: Callable[[], None],
    ):
        self.data_dir = data_dir
        self.python_zip = python_zip
        self.tkinter_src = tkinter_src
        self.scripts_dir = scripts_dir
        self.on_complete = on_complete

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._step_progress: dict[str, float] = {s[0]: 0.0 for s in STEPS}
        self._current_step = ""
        self._gpu_mode = "cpu"
        self._error: str | None = None

        # Selected ASR backends (GigaAM и т.д.) — заполняется в _build_ui,
        # читается в _install_worker на стадии "models".
        self._backend_checkboxes: dict = {}

        self._build_ui()

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

        # Progress bar style
        style.configure(
            "Green.Horizontal.TProgressbar",
            troughcolor=INPUT_BG,
            background=ACCENT,
            thickness=20,
        )

        # ── Title ─────────────────────────────────────────────────────────
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
            text="Первый запуск — установка зависимостей",
            font=("Segoe UI", 10),
            fg=FG_DIM, bg=BG,
        ).pack(anchor="w", pady=(2, 0))

        # ── GPU banner ────────────────────────────────────────────────────
        self.gpu_frame = tk.Frame(self.root, bg="#1a3d2a", padx=12, pady=8)
        self.gpu_frame.pack(fill="x", padx=24, pady=(16, 0))

        self.gpu_label = tk.Label(
            self.gpu_frame,
            text="Определение GPU...",
            font=("Segoe UI", 9, "bold"),
            fg=ACCENT, bg="#1a3d2a",
        )
        self.gpu_label.pack(anchor="w")

        # ── Steps ─────────────────────────────────────────────────────────
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

        # ── Backend checkboxes (ASR models) ───────────────────────────────
        if _BACKEND_INSTALLERS_AVAILABLE and list_backends is not None:
            backends_frame = tk.Frame(self.root, bg=BG)
            backends_frame.pack(fill="x", padx=24, pady=(8, 0))

            tk.Label(
                backends_frame,
                text="Дополнительные модели ASR:",
                font=("Segoe UI", 9, "bold"),
                fg=FG_DIM, bg=BG,
            ).pack(anchor="w")

            for info in list_backends():
                var = tk.BooleanVar(value=info.default_selected)
                self._backend_checkboxes[info.id] = var
                size_mb = info.approx_download_bytes // 1_000_000
                cb = tk.Checkbutton(
                    backends_frame,
                    text=f"{info.title} ({size_mb} MB)",
                    variable=var,
                    bg=BG, fg=FG, selectcolor=BG2,
                    activebackground=BG, activeforeground=FG,
                    font=("Segoe UI", 9),
                )
                cb.pack(anchor="w", pady=(2, 0))
                tk.Label(
                    backends_frame,
                    text=info.description,
                    font=("Segoe UI", 8),
                    fg=FG_DIM, bg=BG,
                    wraplength=560,
                    justify="left",
                ).pack(anchor="w", padx=(20, 0))

        # ── Log area ──────────────────────────────────────────────────────
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

        # ── Overall progress ──────────────────────────────────────────────
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

        # ── Retry button (hidden initially) ───────────────────────────────
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

    def run(self) -> None:
        """Show the window and start installation."""
        self._start_install()
        self._poll_log()
        self.root.mainloop()

    def _start_install(self) -> None:
        """Start (or restart) the installation in a background thread."""
        self.retry_btn.pack_forget()
        self._error = None
        for step_id, _ in STEPS:
            self._step_progress[step_id] = 0.0
            self._step_labels[step_id].config(text="○", fg=FG_DIM)
            self._step_status[step_id].config(text="")
        self._update_overall_progress()

        t = threading.Thread(target=self._install_worker, daemon=True)
        t.start()

    def _install_worker(self) -> None:
        """Run all installation steps in a background thread."""
        try:
            python_dir = self.data_dir / "python"
            python_exe = python_dir / "python.exe"
            ffmpeg_dir = self.data_dir / "tools" / "ffmpeg"

            # Step: Python
            self._begin_step("python")
            if not python_exe.exists():
                # If bundled zip exists, extract. Otherwise download first.
                if not self.python_zip.exists():
                    download_embedded_python(
                        self.python_zip, self._log, self._step_progress_fn("python")
                    )
                extract_embedded_python(
                    self.python_zip, python_dir, self.tkinter_src,
                    self._log, self._step_progress_fn("python"),
                )
            else:
                self._log("Python runtime уже извлечён.")
            self._complete_step("python")

            # Step: pip
            self._begin_step("pip")
            pip_exe = python_dir / "Scripts" / "pip.exe"
            if not pip_exe.exists():
                install_pip(python_exe, self._log, self._step_progress_fn("pip"))
            else:
                self._log("pip уже установлен.")
            self._complete_step("pip")

            # Detect GPU
            self._gpu_mode = detect_gpu(self._log)
            self.root.after(0, self._update_gpu_banner)

            # Step: PyTorch
            self._begin_step("pytorch")
            install_pytorch(
                python_exe, self._gpu_mode,
                self._log, self._step_progress_fn("pytorch"),
            )
            self._complete_step("pytorch")

            # Step: WhisperX
            self._begin_step("whisperx")
            install_whisperx(
                python_exe, self._log, self._step_progress_fn("whisperx"),
            )
            # Re-pin CUDA torch if needed
            if self._gpu_mode == "cuda":
                self._log("Фиксация PyTorch CUDA после WhisperX...")
                repin_pytorch_cuda(python_exe, self._log, lambda p: None)
            self._complete_step("whisperx")

            # Step: ffmpeg
            self._begin_step("ffmpeg")
            download_ffmpeg(
                ffmpeg_dir, self._log, self._step_progress_fn("ffmpeg"),
            )
            self._complete_step("ffmpeg")

            # Step: models (ASR backends like GigaAM)
            self._begin_step("models")
            if _BACKEND_INSTALLERS_AVAILABLE and install_backend is not None:
                selected = [
                    bid for bid, var in self._backend_checkboxes.items()
                    if var.get()
                ]
                if selected:
                    step_cb = self._step_progress_fn("models")
                    for idx, backend_id in enumerate(selected):
                        self._log(f"Установка {backend_id.value}...")

                        def _prog(
                            frac: float,
                            msg: str,
                            _idx: int = idx,
                            _total: int = len(selected),
                            _cb=step_cb,
                        ) -> None:
                            stage_pct = (_idx + frac) / _total * 100
                            _cb(stage_pct)
                            self._log(msg)

                        try:
                            install_backend(backend_id, progress=_prog)
                        except Exception as e:
                            self._log(
                                f"ОШИБКА установки {backend_id.value}: {e}"
                            )
                            raise
                else:
                    self._log("Модели ASR пропущены пользователем.")
            else:
                self._log("Backend installers недоступны — пропуск стадии.")
            self._complete_step("models")

            # Verify
            self._log("")
            info = verify_installation(python_exe, self._log)

            self._log("")
            self._log("=" * 50)
            self._log("  Установка завершена!")
            self._log("=" * 50)

            # Signal completion
            self.root.after(500, self._on_install_complete)

        except Exception as e:
            self._error = str(e)
            self._log(f"\nОШИБКА: {e}")
            self._log(traceback.format_exc())
            self.root.after(0, self._on_install_error)

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
                text="GPU обнаружена — установка в режиме CUDA",
                fg=ACCENT, bg="#1a3d2a",
            )
        else:
            self.gpu_frame.config(bg="#3d3a1a")
            self.gpu_label.config(
                text="GPU не обнаружена — установка в режиме CPU (медленнее)",
                fg=WARN, bg="#3d3a1a",
            )

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

    def _on_install_complete(self) -> None:
        """Called on the main thread after successful installation."""
        self.progress_label.config(
            text="Установка завершена! Запуск приложения...",
            fg=ACCENT,
        )
        self.root.after(1500, self._finish)

    def _on_install_error(self) -> None:
        """Called on the main thread after a failed installation."""
        self.progress_label.config(
            text=f"Ошибка установки",
            fg=ERR,
        )
        # Mark current step as failed
        if self._current_step:
            self._step_labels[self._current_step].config(text="✗", fg=ERR)
            self._step_status[self._current_step].config(text="Ошибка", fg=ERR)
        # Show retry button
        self.retry_btn.pack(pady=(10, 0))

    def _finish(self) -> None:
        """Destroy installer window and call completion callback."""
        self.root.destroy()
        self.on_complete()

    def _on_close(self) -> None:
        """Handle window close — ask confirmation during installation."""
        if self._current_step and not self._error:
            # Installation in progress — ignore close
            return
        self.root.destroy()
