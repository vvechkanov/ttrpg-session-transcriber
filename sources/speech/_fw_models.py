"""Pinned HF model file manifests for faster-whisper backend.

Отдельный файл от :mod:`_fw_wheels` потому что веса моделей и
python-пакеты качаются разными URL-ами (HF resolve/main для моделей vs
files.pythonhosted.org для wheel-ов). Логически же они — часть одной
раскладки backend-а.

Раскладка на диске (см. :func:`sources.speech._fw_paths.fw_model_dir`)::

    <backend_dir>/models/
        config.json
        preprocessor_config.json
        tokenizer.json
        vocabulary.json
        model.bin                    ← LFS, ~3 GB

При добавлении новой модели:
    1. Фетчим ``/api/models/<repo>/tree/main?expand=True`` от HF.
    2. Для LFS файлов берём ``lfs.oid`` как sha256 (HF хранит sha256 oid
       у LFS pointer-ов напрямую).
    3. Для не-LFS файлов (config.json и т.п.) качаем и считаем sha256
       локально — git blob hash из HF API не подходит.
    4. Добавляем запись в ``FW_MODEL_BUNDLES``.

``FW_MODEL_BUNDLES`` — это словарь ``{hf_repo_id → tuple[ModelFile, ...]}``.
Install-поток выбирает нужную запись по ``params.model``.
"""

from __future__ import annotations

from sources.speech._bundle_download import RemoteFile

#: Ключ каталога моделей внутри backend dir. Файлы кладутся в
#: ``<backend_dir>/models/`` (см. ``_fw_paths.fw_model_dir``). Это же
#: значение используется как ``relpath`` для RemoteFile — generic
#: installer умеет класть файл в поддиректорию через relpath.
_MODELS_RELDIR = "models"


def _model_file(
    hf_repo: str,
    filename: str,
    sha256: str,
    size: int,
) -> RemoteFile:
    """Shortcut for a plain HF resolve/main download."""
    return RemoteFile(
        url=f"https://huggingface.co/{hf_repo}/resolve/main/{filename}",
        relpath=f"{_MODELS_RELDIR}/{filename}",
        sha256=sha256,
        size=size,
        logical=filename,
        unpack="none",
    )


#: Для каждой поддерживаемой модели — список файлов с pinned sha256.
#: Ключ — HF repo ID, который пользователь задаёт в
#: ``FasterWhisperInstallParams.model``.
FW_MODEL_BUNDLES: dict[str, tuple[RemoteFile, ...]] = {
    "bzikst/faster-whisper-large-v3-ru-podlodka": (
        _model_file(
            hf_repo="bzikst/faster-whisper-large-v3-ru-podlodka",
            filename="config.json",
            sha256="a9306624f5ec14270a014b647e5c316b6e03a662c369758d1b90697a7b0655b9",
            size=2394,
        ),
        _model_file(
            hf_repo="bzikst/faster-whisper-large-v3-ru-podlodka",
            filename="preprocessor_config.json",
            sha256="7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711",
            size=340,
        ),
        _model_file(
            hf_repo="bzikst/faster-whisper-large-v3-ru-podlodka",
            filename="tokenizer.json",
            sha256="6d8cbd7cd0d8d5815e478dac67b85a26bbe77c1f5e0c6d76d1ce2abc0e5f21ca",
            size=2480617,
        ),
        _model_file(
            hf_repo="bzikst/faster-whisper-large-v3-ru-podlodka",
            filename="vocabulary.json",
            sha256="c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1",
            size=1068114,
        ),
        _model_file(
            hf_repo="bzikst/faster-whisper-large-v3-ru-podlodka",
            filename="model.bin",
            # LFS oid = sha256 of content (HF stores it directly).
            sha256="8661ebf2a7dcd3c785c6cfa7fff6822c600eb2a3a33a9e85184de627bf08f581",
            size=3087284276,
        ),
    ),
}


def get_model_bundle(model_id: str) -> tuple[RemoteFile, ...]:
    """Вернуть список файлов модели по ID.

    Raises:
        KeyError: если модель не зарегистрирована. Сообщение содержит
            список поддерживаемых ID для диагностики.
    """
    try:
        return FW_MODEL_BUNDLES[model_id]
    except KeyError as exc:
        raise KeyError(
            f"Unknown faster-whisper model: {model_id!r}. "
            f"Supported: {sorted(FW_MODEL_BUNDLES)}"
        ) from exc
