"""Тесты ``ui.shell.settings_drawer.SettingsDrawer`` (Phase 2, ADR-016).

Покрытие:
    * ``open_with_panel`` требует объект, реализующий
      :class:`SettingsPanelProtocol` — иначе ``TypeError``;
    * геометрия drawer'а при открытии = 80 % ширины главного окна,
      прижат к правому краю, высота = высоте окна;
    * backdrop показывается при открытии и покрывает всё окно;
    * клик по backdrop'у закрывает drawer (и эмитит ``cancelled``);
    * сигнал ``panel.changed`` обновляет dirty-индикатор в footer и
      включает кнопку [Сохранить];
    * ``[Сохранить]`` вызывает ``validate()`` и затем ``apply_changes()``
      и эмитит ``saved``;
    * ресайз главного окна пересчитывает backdrop и drawer (drawer
      по-прежнему 80 % ширины нового размера окна).

Все тесты помечены ``gui`` — ``pytest -m "not gui"`` их пропустит. В
CI до фазы 9 GUI-тесты выключены; на разработчике они запускаются
через ``QT_QPA_PLATFORM=offscreen``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QMainWindow, QWidget

from core.ui_contract import SettingsPanelProtocol  # noqa: F401  (используется в ассертах типов)
from ui.shell._demo_stub_panel import DemoStubPanel
from ui.shell.settings_drawer import SettingsDrawer


# ── Вспомогательная фабрика окна ───────────────────────────────────────


def _make_window(qtbot, *, width: int = 1400, height: int = 900) -> QMainWindow:
    window = QMainWindow()
    window.resize(width, height)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def _finish_animation(drawer: SettingsDrawer, qtbot) -> None:
    """Дождаться завершения анимации drawer'а без реального сна.

    Если анимация ещё идёт — ждём её завершения через сигнал.
    Если уже закончилась — сразу возвращаемся.
    """
    anim = drawer._animation  # noqa: SLF001 — тест намеренно лезет внутрь
    if anim.state() == QPropertyAnimation.State.Running:
        with qtbot.waitSignal(anim.finished, timeout=2000):
            pass


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.gui
class TestProtocolEnforcement:
    def test_panel_without_protocol_raises_typeerror(self, qtbot):
        window = _make_window(qtbot)
        drawer = SettingsDrawer(window)

        class NotAPanel(QWidget):
            """Не имеет ``changed``/``validate``/..."""

        bad = NotAPanel()
        qtbot.addWidget(bad)

        with pytest.raises(TypeError, match="SettingsPanelProtocol"):
            drawer.open_with_panel(bad, title="x")

    def test_panel_with_protocol_opens_without_error(self, qtbot):
        window = _make_window(qtbot)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="Демо", subtitle="stub")
        _finish_animation(drawer, qtbot)

        assert drawer.is_open()


@pytest.mark.gui
class TestGeometry:
    def test_drawer_width_is_80_percent_of_window(self, qtbot):
        window = _make_window(qtbot, width=1400, height=900)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        expected_w = int(1400 * SettingsDrawer.WIDTH_RATIO)
        geom = drawer.geometry()
        assert geom.width() == expected_w
        assert geom.height() == 900
        # Прижат к правому краю: x + width == window width
        assert geom.x() + geom.width() == 1400
        assert geom.y() == 0

    def test_drawer_has_min_width_320_on_narrow_window(self, qtbot):
        """На очень узком окне drawer не уже 320 px (floor)."""
        window = _make_window(qtbot, width=360, height=600)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        # 360 * 0.8 = 288, но мин. 320
        assert drawer.geometry().width() == 320


@pytest.mark.gui
class TestBackdrop:
    def test_backdrop_visible_after_open(self, qtbot):
        window = _make_window(qtbot)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        assert not drawer._backdrop.isVisible()  # noqa: SLF001

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        assert drawer._backdrop.isVisible()  # noqa: SLF001

    def test_backdrop_covers_entire_window(self, qtbot):
        window = _make_window(qtbot, width=1200, height=800)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        bd_geom = drawer._backdrop.geometry()  # noqa: SLF001
        assert bd_geom.x() == 0
        assert bd_geom.y() == 0
        assert bd_geom.width() == 1200
        assert bd_geom.height() == 800

    def test_backdrop_click_closes_drawer_when_clean(self, qtbot):
        window = _make_window(qtbot)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        with qtbot.waitSignal(drawer.cancelled, timeout=2000):
            # Эмулируем клик по backdrop'у напрямую — мышиный клик
            # не доставляется оффскрин-платформой надёжно.
            drawer._backdrop.clicked.emit()  # noqa: SLF001
            _finish_animation(drawer, qtbot)

        assert not drawer.is_open()
        assert not drawer._backdrop.isVisible()  # noqa: SLF001


@pytest.mark.gui
class TestDirtyIndicator:
    def test_clean_panel_save_disabled(self, qtbot):
        window = _make_window(qtbot)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        assert not drawer._save_button.isEnabled()  # noqa: SLF001
        assert drawer._dirty_label.text() == ""  # noqa: SLF001

    def test_panel_change_enables_save_and_shows_indicator(self, qtbot):
        window = _make_window(qtbot)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        # Правим данные в панели → changed emit → dirty
        panel._line.setText("новый текст")  # noqa: SLF001

        assert drawer._save_button.isEnabled()  # noqa: SLF001
        assert "несохранённые" in drawer._dirty_label.text().lower()  # noqa: SLF001

    def test_revert_clears_dirty(self, qtbot):
        """Если пользователь откатил изменение вручную — dirty снимается."""
        window = _make_window(qtbot)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        panel._line.setText("abc")  # noqa: SLF001
        assert drawer._save_button.isEnabled()  # noqa: SLF001

        panel._line.setText("")  # noqa: SLF001 — вернулись к исходному
        assert not drawer._save_button.isEnabled()  # noqa: SLF001


@pytest.mark.gui
class TestSaveCancelFlow:
    def test_save_calls_apply_and_closes(self, qtbot):
        window = _make_window(qtbot)
        drawer = SettingsDrawer(window)

        calls: list[str] = []

        class SpyPanel(QWidget):
            changed = Signal()

            def validate(self) -> list[str]:
                calls.append("validate")
                return []

            def apply_changes(self) -> None:
                calls.append("apply")

            def has_unsaved_changes(self) -> bool:
                return True

        panel = SpyPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)
        # Эмулируем изменение чтобы кнопка включилась
        panel.changed.emit()

        with qtbot.waitSignal(drawer.saved, timeout=2000):
            drawer._on_save_clicked()  # noqa: SLF001
            _finish_animation(drawer, qtbot)

        assert calls == ["validate", "apply"]
        assert not drawer.is_open()

    def test_save_with_validation_errors_does_not_apply(self, qtbot, monkeypatch):
        window = _make_window(qtbot)
        drawer = SettingsDrawer(window)

        calls: list[str] = []

        class FailingPanel(QWidget):
            changed = Signal()

            def validate(self) -> list[str]:
                calls.append("validate")
                return ["поле X не заполнено"]

            def apply_changes(self) -> None:
                calls.append("apply")

            def has_unsaved_changes(self) -> bool:
                return True

        panel = FailingPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        # Заглушаем модальный QMessageBox — иначе тест повиснет
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Ok)

        drawer._on_save_clicked()  # noqa: SLF001

        assert calls == ["validate"]  # apply НЕ вызван
        assert drawer.is_open()  # drawer остался открыт


@pytest.mark.gui
class TestResize:
    def test_resize_main_window_recalculates_drawer(self, qtbot):
        window = _make_window(qtbot, width=1400, height=900)
        drawer = SettingsDrawer(window)
        panel = DemoStubPanel()
        qtbot.addWidget(panel)

        drawer.open_with_panel(panel, title="x")
        _finish_animation(drawer, qtbot)

        assert drawer.geometry().width() == int(1400 * SettingsDrawer.WIDTH_RATIO)

        # Эмулируем ресайз: resize() → QResizeEvent прилетает на окно,
        # event filter drawer'а его ловит. Форсим через sendEvent чтобы не
        # зависеть от event loop'а.
        window.resize(1000, 700)
        from PySide6.QtWidgets import QApplication

        QApplication.sendEvent(
            window,
            QResizeEvent(QSize(1000, 700), QSize(1400, 900)),
        )

        assert drawer.geometry().width() == int(1000 * SettingsDrawer.WIDTH_RATIO)
        assert drawer.geometry().height() == 700
        # По-прежнему прижат к правому краю
        assert drawer.geometry().x() + drawer.geometry().width() == 1000
        # Backdrop тоже перестроился
        assert drawer._backdrop.geometry().width() == 1000  # noqa: SLF001
        assert drawer._backdrop.geometry().height() == 700  # noqa: SLF001
