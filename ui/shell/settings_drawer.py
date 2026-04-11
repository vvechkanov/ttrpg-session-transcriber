"""SettingsDrawer — всплывающая боковая панель для ``[Настроить]``.

Реализует хост-контракт из ADR-016 §SettingsDrawer lifecycle. Drawer —
это ``QFrame`` с ``parent=main_window``, НЕ добавленный в layout:
живёт как absolute-позиционированный оверлей поверх главного контента.

Паттерн — Android navigation drawer / гамбургер-меню:
    - ширина **80%** от текущей ширины главного окна (адаптивно);
    - полупрозрачный backdrop (``rgba(45,37,32,0.25)``) покрывает **всё
      окно** за drawer'ом, клик по backdrop'у → отмена;
    - анимация выезда справа (220 мс, OutCubic) через
      ``QPropertyAnimation``;
    - основной контент НЕ сдвигается — drawer ложится поверх.

Контент drawer'а (форма настроек модуля) приходит от темплейта через
``open_with_panel(panel, ...)`` и должен удовлетворять
``core.ui_contract.SettingsPanelProtocol``. Хост сам рисует sticky
header (иконка/заголовок/подзаголовок/крестик) и sticky footer
(dirty-индикатор + ``[Отмена]`` / ``[Сохранить]``).

См. также:
    - ``docs/adr/ADR-016-module-ui-contract.md`` §SettingsDrawer lifecycle
    - ``docs/design/screen-3-session.md`` §9
    - ``docs/design/mockups/figma-make/.../components/SidePanel.tsx``
      — канонический TSX-референс поведения и токенов
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.ui_contract import SettingsPanelProtocol

# ── Design tokens (см. Figma v1 theme.css) ─────────────────────────────
_COLOR_CARD = "#FFFFFF"
_COLOR_FOREGROUND = "#2D2520"
_COLOR_MUTED_FG = "#6B625A"
_COLOR_ACCENT = "#D4843B"
_COLOR_ACCENT_FG = "#FFFFFF"
_COLOR_SECONDARY = "#F5F2EF"
_COLOR_MUTED = "#E8E4DF"
_COLOR_BORDER = "rgba(107, 98, 90, 0.15)"
# foreground @ 25% alpha = 2D2520 → rgba(45,37,32,0.25)
_COLOR_BACKDROP = "rgba(45, 37, 32, 0.25)"

_RADIUS_PX = 10
_HEADER_PAD_PX = 24
_FOOTER_PAD_PX = 20
_CONTENT_PAD_PX = 24


class _DrawerBackdrop(QWidget):
    """Полноэкранный полупрозрачный слой за drawer'ом.

    Ловит клики по «остальной части экрана» и эмитит
    :attr:`clicked` — host drawer слушает и инициирует закрытие.
    """

    clicked = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(True)
        self.setStyleSheet(f"background-color: {_COLOR_BACKDROP};")
        self.hide()

    def mousePressEvent(self, event) -> None:  # noqa: D401 — Qt override
        self.clicked.emit()
        event.accept()


class SettingsDrawer(QFrame):
    """Overlay drawer hosting settings panels for pipeline modules.

    Lifecycle (см. ADR-016 §SettingsDrawer lifecycle):
        1. ``open_with_panel(panel, title, subtitle)`` — вставляет
           ``panel`` в scroll area, запускает анимацию, подписывается
           на ``panel.changed``.
        2. ``panel.changed`` → обновление dirty-индикатора в footer,
           активация кнопки ``[Сохранить]``.
        3. Клик ``[Сохранить]`` → ``panel.validate()``. Пусто →
           ``panel.apply_changes()`` → анимация закрытия. Непусто →
           диалог с ошибками, drawer остаётся открытым.
        4. Клик ``[Отмена]`` / Esc / backdrop → если
           ``panel.has_unsaved_changes()`` → модальное подтверждение.
    """

    # 80% ширины родительского окна. См. явное требование пользователя;
    # если понадобится 480 px фикс — меняй эту константу на целочисленное
    # значение и добавь ветку в ``_drawer_target_rect``.
    WIDTH_RATIO: float = 0.80

    #: Длительность анимации в миллисекундах
    ANIMATION_MS: int = 220

    #: Сигнал: пользователь сохранил изменения. Шелл слушает для
    #: перерисовки карточек (если модуль изменился).
    saved = Signal()

    #: Сигнал: drawer закрыт без сохранения.
    cancelled = Signal()

    def __init__(self, main_window: QMainWindow) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._panel: QWidget | None = None
        self._is_open = False
        self._is_dirty = False

        # Backdrop — отдельный sibling поверх главного окна
        self._backdrop = _DrawerBackdrop(main_window)
        self._backdrop.clicked.connect(self._on_cancel_clicked)

        # Сам drawer
        self.setObjectName("settingsDrawer")
        self.setAutoFillBackground(True)
        self.setStyleSheet(self._drawer_stylesheet())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        # Layout drawer'а: header | scroll | footer
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._header = self._build_header()
        root.addWidget(self._header)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {_COLOR_CARD}; border: none; }}"
        )
        root.addWidget(self._scroll, stretch=1)

        self._footer = self._build_footer()
        root.addWidget(self._footer)

        # Анимация геометрии
        self._animation = QPropertyAnimation(self, b"geometry")
        self._animation.setDuration(self.ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.finished.connect(self._on_animation_finished)

        # Следим за ресайзом главного окна, чтобы подстраивать drawer
        main_window.installEventFilter(self)

    # ── Public API ─────────────────────────────────────────────────

    def open_with_panel(
        self,
        panel: QWidget,
        *,
        title: str,
        subtitle: str = "",
    ) -> None:
        """Показать drawer с содержимым ``panel``.

        Args:
            panel: виджет формы, возвращённый
                ``make_settings_panel(...)`` темплейта модуля. Должен
                реализовывать :class:`SettingsPanelProtocol`.
            title: текст в sticky header (например, «Настройки · Аудио»).
            subtitle: опциональный подзаголовок под title'ом (например,
                «GigaAM-v3 RNNT · русский»).

        Raises:
            TypeError: если ``panel`` не реализует
                :class:`SettingsPanelProtocol`.
        """
        if not isinstance(panel, SettingsPanelProtocol):
            raise TypeError(
                f"panel must implement SettingsPanelProtocol, got "
                f"{type(panel).__name__}"
            )

        if self._is_open:
            # По контракту MVP — один drawer за раз; закрываем предыдущий
            # синхронно без подтверждения.
            self._detach_panel()

        self._panel = panel
        # Сразу подключаемся к сигналу изменений панели
        panel.changed.connect(self._on_panel_changed)  # type: ignore[attr-defined]

        self._scroll.setWidget(panel)
        self._scroll.verticalScrollBar().setValue(0)

        self._set_header_text(title, subtitle)
        self._set_dirty(False)

        self._show_and_animate_in()
        self._is_open = True

    def close_drawer(self, *, force: bool = False) -> None:
        """Закрыть drawer.

        Args:
            force: если ``True`` — не спрашивать подтверждения даже при
                ``has_unsaved_changes()``. Используется хостом когда
                приложение само закрывается.
        """
        if not self._is_open:
            return
        if not force and not self._confirm_close_if_dirty():
            return
        self._animate_out_and_cleanup()

    def is_open(self) -> bool:
        return self._is_open

    # ── Header/Footer building ─────────────────────────────────────

    def _build_header(self) -> QWidget:
        w = QWidget(self)
        w.setObjectName("drawerHeader")
        w.setStyleSheet(
            f"""
            #drawerHeader {{
                background-color: {_COLOR_CARD};
                border-bottom: 1px solid {_COLOR_BORDER};
            }}
            """
        )
        layout = QHBoxLayout(w)
        layout.setContentsMargins(
            _HEADER_PAD_PX, _HEADER_PAD_PX, _HEADER_PAD_PX, _HEADER_PAD_PX
        )
        layout.setSpacing(12)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(4)

        self._title_label = QLabel("", w)
        self._title_label.setStyleSheet(
            f"color: {_COLOR_FOREGROUND}; font-size: 18px; font-weight: 500;"
        )
        texts.addWidget(self._title_label)

        self._subtitle_label = QLabel("", w)
        self._subtitle_label.setStyleSheet(
            f"color: {_COLOR_MUTED_FG}; font-size: 13px;"
        )
        texts.addWidget(self._subtitle_label)

        layout.addLayout(texts, stretch=1)

        self._close_button = QPushButton("×", w)
        self._close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_button.setFixedSize(32, 32)
        self._close_button.setStyleSheet(
            f"""
            QPushButton {{
                color: {_COLOR_MUTED_FG};
                background: transparent;
                border: none;
                font-size: 22px;
            }}
            QPushButton:hover {{
                color: {_COLOR_FOREGROUND};
            }}
            """
        )
        self._close_button.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self._close_button, alignment=Qt.AlignmentFlag.AlignTop)

        return w

    def _build_footer(self) -> QWidget:
        w = QWidget(self)
        w.setObjectName("drawerFooter")
        w.setStyleSheet(
            f"""
            #drawerFooter {{
                background-color: {_COLOR_CARD};
                border-top: 1px solid {_COLOR_BORDER};
            }}
            """
        )
        layout = QHBoxLayout(w)
        layout.setContentsMargins(
            _FOOTER_PAD_PX, _FOOTER_PAD_PX, _FOOTER_PAD_PX, _FOOTER_PAD_PX
        )
        layout.setSpacing(12)

        self._dirty_label = QLabel("", w)
        self._dirty_label.setStyleSheet(
            f"color: {_COLOR_ACCENT}; font-size: 13px;"
        )
        layout.addWidget(self._dirty_label, stretch=1)

        self._cancel_button = QPushButton("Отмена", w)
        self._cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_button.setStyleSheet(
            f"""
            QPushButton {{
                color: {_COLOR_FOREGROUND};
                background: transparent;
                border: 1px solid transparent;
                padding: 8px 16px;
                border-radius: {_RADIUS_PX - 2}px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {_COLOR_SECONDARY};
            }}
            """
        )
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self._cancel_button)

        self._save_button = QPushButton("Сохранить", w)
        self._save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_button.setEnabled(False)
        self._save_button.setStyleSheet(self._save_button_stylesheet(enabled=False))
        self._save_button.clicked.connect(self._on_save_clicked)
        layout.addWidget(self._save_button)

        return w

    @staticmethod
    def _save_button_stylesheet(*, enabled: bool) -> str:
        if enabled:
            return f"""
                QPushButton {{
                    color: {_COLOR_ACCENT_FG};
                    background-color: {_COLOR_ACCENT};
                    border: none;
                    padding: 8px 16px;
                    border-radius: {_RADIUS_PX - 2}px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: #C27431;
                }}
            """
        return f"""
            QPushButton {{
                color: {_COLOR_MUTED_FG};
                background-color: {_COLOR_MUTED};
                border: none;
                padding: 8px 16px;
                border-radius: {_RADIUS_PX - 2}px;
                font-size: 14px;
                font-weight: 500;
            }}
        """

    @staticmethod
    def _drawer_stylesheet() -> str:
        return f"""
            QFrame#settingsDrawer {{
                background-color: {_COLOR_CARD};
                border-left: 1px solid {_COLOR_BORDER};
            }}
        """

    def _set_header_text(self, title: str, subtitle: str) -> None:
        self._title_label.setText(title)
        self._subtitle_label.setText(subtitle)
        self._subtitle_label.setVisible(bool(subtitle))

    # ── Geometry ──────────────────────────────────────────────────

    def _drawer_target_rect(self) -> QRect:
        """Куда drawer должен встать после окончания анимации open."""
        w = self._main_window.width()
        h = self._main_window.height()
        drawer_w = max(320, int(w * self.WIDTH_RATIO))  # нижняя граница — 320 px
        return QRect(w - drawer_w, 0, drawer_w, h)

    def _drawer_offscreen_rect(self) -> QRect:
        """Стартовая позиция — drawer за правым краем окна."""
        w = self._main_window.width()
        h = self._main_window.height()
        drawer_w = max(320, int(w * self.WIDTH_RATIO))
        return QRect(w, 0, drawer_w, h)

    def _backdrop_rect(self) -> QRect:
        """Backdrop покрывает всё окно."""
        return QRect(0, 0, self._main_window.width(), self._main_window.height())

    # ── Open / close animation ─────────────────────────────────────

    def _show_and_animate_in(self) -> None:
        self._backdrop.setGeometry(self._backdrop_rect())
        self._backdrop.show()
        self._backdrop.raise_()

        self.setGeometry(self._drawer_offscreen_rect())
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

        self._animation.stop()
        self._animation.setStartValue(self._drawer_offscreen_rect())
        self._animation.setEndValue(self._drawer_target_rect())
        self._animation.setDirection(QPropertyAnimation.Direction.Forward)
        self._animation.start()

    def _animate_out_and_cleanup(self) -> None:
        if not self._is_open:
            return
        self._is_open = False  # set early to guard against re-entry

        self._animation.stop()
        self._animation.setStartValue(self.geometry())
        self._animation.setEndValue(self._drawer_offscreen_rect())
        self._animation.setDirection(QPropertyAnimation.Direction.Forward)
        self._animation.start()

    def _on_animation_finished(self) -> None:
        if not self._is_open:
            # Это был animate-out — прячем всё и отвязываем panel
            self.hide()
            self._backdrop.hide()
            self._detach_panel()

    def _detach_panel(self) -> None:
        if self._panel is None:
            return
        try:
            self._panel.changed.disconnect(self._on_panel_changed)  # type: ignore[attr-defined]
        except (TypeError, RuntimeError):
            # disconnect вызывает TypeError если не подключено
            pass
        # Убираем виджет из scroll area. takeWidget отдаёт ownership обратно.
        extracted = self._scroll.takeWidget()
        if extracted is not None:
            extracted.setParent(None)
        self._panel = None
        self._set_dirty(False)

    # ── Dirty state ───────────────────────────────────────────────

    def _on_panel_changed(self) -> None:
        if self._panel is None:
            return
        self._set_dirty(cast(SettingsPanelProtocol, self._panel).has_unsaved_changes())

    def _set_dirty(self, dirty: bool) -> None:
        self._is_dirty = dirty
        self._dirty_label.setText(
            "● Есть несохранённые изменения" if dirty else ""
        )
        self._save_button.setEnabled(dirty)
        self._save_button.setStyleSheet(self._save_button_stylesheet(enabled=dirty))

    # ── Save / Cancel handlers ─────────────────────────────────────

    def _on_save_clicked(self) -> None:
        if not self._try_save():
            return
        self.saved.emit()
        self._animate_out_and_cleanup()

    def _try_save(self) -> bool:
        """Validate → apply. Вернуть ``True`` если сохранение прошло."""
        if self._panel is None:
            return True
        panel = cast(SettingsPanelProtocol, self._panel)
        errors = panel.validate()
        if errors:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Ошибки в настройках")
            box.setText("Исправьте ошибки перед сохранением:")
            box.setDetailedText("\n".join(f"• {e}" for e in errors))
            box.exec()
            return False
        panel.apply_changes()
        return True

    def _on_cancel_clicked(self) -> None:
        if not self._confirm_close_if_dirty():
            return
        self.cancelled.emit()
        self._animate_out_and_cleanup()

    def _confirm_close_if_dirty(self) -> bool:
        """Показать подтверждение если dirty. True = можно закрывать."""
        if self._panel is None:
            return True
        panel = cast(SettingsPanelProtocol, self._panel)
        if not panel.has_unsaved_changes():
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Несохранённые изменения")
        box.setText("Сохранить изменения перед закрытием?")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        result = box.exec()
        if result == QMessageBox.StandardButton.Save:
            return self._try_save()
        if result == QMessageBox.StandardButton.Discard:
            return True
        return False  # Cancel

    # ── Keyboard / event filter ────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self._on_cancel_clicked()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Подстраиваемся под ресайз главного окна
        if obj is self._main_window and event.type() == QEvent.Type.Resize:
            self._backdrop.setGeometry(self._backdrop_rect())
            if self._is_open:
                # Во время анимации стопаем и снапаем к финальной позиции
                if self._animation.state() == QPropertyAnimation.State.Running:
                    self._animation.stop()
                self.setGeometry(self._drawer_target_rect())
        return super().eventFilter(obj, event)
