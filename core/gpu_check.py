"""GPU pre-flight check, lazy torch import."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def check_gpu_or_warn(device: str) -> None:
    """If device == 'cuda', verify torch.cuda is available and log warning if not.

    Does NOT raise, does NOT downgrade. Caller decides.
    """
    if device != "cuda":
        return
    try:
        import torch  # lazy
    except ImportError:
        logger.warning("device='cuda' but torch is not installed")
        return
    if not torch.cuda.is_available():
        logger.warning("device='cuda' but torch.cuda.is_available() is False")
