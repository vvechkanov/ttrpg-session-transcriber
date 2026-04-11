"""Абстрактный Source — извлечение аннотаций из session_dir.

Также содержит ``Installable`` Protocol — ортогональную способность
конкретных Source-ов устанавливать свои runtime-зависимости (модели,
вспомогательные файлы). См. ``docs/specs/gigaam-v2.md`` §2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from domain.annotations import Annotation


class Source(ABC):
    """Абстрактный источник аннотаций.

    Каждый наследник реализует ``extract(session_dir)`` и возвращает плоский
    список ``Annotation`` (``SpeechSegment``/``EmotionTag``/``ChatMessage``/
    ``GameLogEntry``) — тип зависит от конкретного источника.
    """

    name: str

    @abstractmethod
    def extract(self, session_dir: Path) -> list[Annotation]:
        """Извлечь аннотации из ``session_dir``."""
        ...


# Progress callback: (fraction_0_to_1, human_readable_message) -> None.
# Вызывается из worker-thread. UI-клиент обязан сам пробрасывать результаты
# в main-thread (через queue/after). Throttling — обязанность вызывающей
# стороны (того, кто дёргает .install()), а не самого Installable.install():
# Source может вызывать callback часто.
InstallProgress = Callable[[float, str], None]


@runtime_checkable
class Installable(Protocol):
    """Способность source-а устанавливать свои runtime-зависимости.

    Реализации ДОЛЖНЫ быть идемпотентными: повторный ``install()`` на
    корректно установленную версию — no-op (быстрая проверка через
    ``is_installed``). Некорректная/частичная установка восстанавливается
    ``install()``-ом без отдельного repair()/upgrade().

    Параметры установки (``params``) — per-module dataclass. Вызывающая
    сторона (``core.backend_installers``) знает конкретный тип; на уровне
    Protocol тип остаётся ``object`` из-за отсутствия TypeVar-variance
    в структурной типизации. См. gigaam-v2.md §2.4.

    **Tracked install invariant (Epic A):** всё, что ``install()``
    пишет на диск, ДОЛЖНО лежать строго внутри одного каталога —
    «корневой каталог backend-а». Никаких глобальных кешей
    (``~/.cache/huggingface``, ``~/.cache/torch``, site-packages
    системного Python и т.п.): каждый backend обязан изолировать
    свои файлы и веса в собственной поддиректории под
    ``default_models_root()``. Это делает ``uninstall()`` простым
    и безопасным — один ``shutil.rmtree`` на корневую директорию.
    """

    def is_installed(self, params: object) -> bool:
        ...

    def install(
        self,
        params: object,
        progress: InstallProgress | None = None,
    ) -> None:
        ...

    def uninstall(self, params: object) -> None:
        """Удалить все файлы, созданные ``install(params)``.

        Контракт:
            * После успешного ``uninstall(params)`` ``is_installed(params)``
              ДОЛЖЕН вернуть False.
            * Должна быть идемпотентной: вызов на неустановленный
              backend — no-op (не бросает).
            * НЕ трогает ничего за пределами корневого каталога
              backend-а (см. tracked install invariant выше).

        Реализация как правило сводится к ``shutil.rmtree`` корневой
        директории backend-а — поэтому invariant выше критичен.
        """
        ...

    def installed_size_bytes(self, params: object) -> int:
        """Суммарный размер установленных файлов в байтах.

        Если не установлено — возвращает 0.
        """
        ...
