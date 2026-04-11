"""Пути для faster-whisper backend (Epic A tracked install).

Раскладка на диске (see also ``_bundle_download.BundleSpec``)::

    <models_root>/faster-whisper/<model-slug>/
        site-packages/               ← распакованные wheel-ы pip-closure
            faster_whisper/
            ctranslate2/
            ...
        models/                      ← HF snapshot для выбранной модели
            model.bin
            tokenizer.json
            ...
        version.json                 ← пишется ПОСЛЕДНИМ (completeness)

Всё, что пишется install-ом, лежит строго под этим корневым каталогом.
``uninstall()`` = ``shutil.rmtree(fw_module_dir(params))``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from sources.speech._gigaam_paths import default_models_root

if TYPE_CHECKING:
    from sources.speech.faster_whisper import FasterWhisperInstallParams


#: Bump при несовместимом изменении раскладки (например, добавлении
#: поддиректорий, переименовании ``site-packages``). ``is_installed``
#: сверяет это значение с version.json и требует переустановки при
#: расхождении.
FW_SCHEMA_VERSION = 1


_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def model_slug(model_id: str) -> str:
    """Привести HF model ID к filesystem-safe slug.

    Примеры:
        ``"bzikst/faster-whisper-large-v3-ru-podlodka"`` →
            ``"bzikst__faster-whisper-large-v3-ru-podlodka"``
        ``"large-v3"`` → ``"large-v3"``

    Слэши заменяются на двойное подчёркивание, всё кроме
    ``[A-Za-z0-9._-]`` и ``/`` — на одинарное подчёркивание.
    """
    safe = model_id.replace("/", "__")
    safe = _SLUG_RE.sub("_", safe)
    return safe or "default"


def fw_module_dir(params: "FasterWhisperInstallParams") -> Path:
    """Каталог одного установленного faster-whisper backend-а.

    Один каталог = один (model_id) install. Разные модели (например,
    ``large-v3-ru-podlodka`` и ``medium``) получают разные каталоги и
    устанавливаются/удаляются независимо.
    """
    root = params.models_root or default_models_root()
    return root / "faster-whisper" / model_slug(params.model)


def fw_site_packages(params: "FasterWhisperInstallParams") -> Path:
    """Путь к ``site-packages`` внутри backend dir.

    Runtime-код должен вставить этот путь в ``sys.path`` перед первым
    импортом ``faster_whisper``.
    """
    return fw_module_dir(params) / "site-packages"


def fw_model_dir(params: "FasterWhisperInstallParams") -> Path:
    """Путь к HF snapshot (model.bin, tokenizer.json, ...)."""
    return fw_module_dir(params) / "models"
