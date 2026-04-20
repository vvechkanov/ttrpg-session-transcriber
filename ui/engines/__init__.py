"""Threaded engine adapters between ``core/`` and QML.

QThread-moved worker objects run the real ASR and merger pipelines in
the background so the UI thread stays responsive (phase-bar animations,
live progress, cancel button). All public signals land on the main
thread via Qt's default auto-connection type.

Step 5 (this slice) ships a simulated ``AsrWorker`` + ``PipelineController``
so the UI can exercise the progress / done / cancel flow end-to-end.
Step 6 swaps the simulated loop for a real ``core.asr`` call.
"""

from ui.engines.asr_worker import AsrWorker
from ui.engines.install_worker import InstallWorker
from ui.engines.merger_worker import MergerWorker
from ui.engines.pipeline_controller import PipelineController

__all__ = ["AsrWorker", "InstallWorker", "MergerWorker", "PipelineController"]
