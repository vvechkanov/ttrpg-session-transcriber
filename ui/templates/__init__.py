"""UI шаблоны для модулей pipeline (Module UI Contract, ADR-016).

Каждый файл ``*_template.py`` в этом пакете экспортирует три фабрики
виджетов:

    def make_home_card(parent, module, state, params) -> QWidget
    def make_runtime_panel(parent, module, state, params) -> QWidget
    def make_settings_panel(parent, module, state, params) -> QWidget

Резолв — через ``core.ui_registry.resolve_template(ui_config)``.

Сам пакет ничего не экспортирует (импорты ленивые), чтобы загрузка
``ui.templates`` не тянула в память все темплейты сразу.
"""
