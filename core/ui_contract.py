"""Module UI Contract — neutral types shared between modules and UI.

THIS FILE IS A PLACEHOLDER. It will be filled by the architect agent per
ADR-016 (Module UI Contract). Until then, modules that want to declare
ui_config should wait. Nothing in this file is stable yet.

Layer rule: this file MUST remain free of PySide6 imports. It is
imported from `sources/`, `mergers/`, `renderers/`, and any such import
of Qt would create a layer violation.
"""

# TODO(ADR-016): define UIConfig dataclass (template: str, params: dict, visible: bool)
# TODO(ADR-016): define SettingsPanelProtocol
