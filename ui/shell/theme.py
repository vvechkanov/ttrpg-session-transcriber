"""Figma v1 design tokens — единственный источник правды для цветов,
радиусов и отступов Qt-UI.

Значения взяты из
``docs/design/mockups/figma-make/screen-3-session/v1/src/styles/theme.css``
и должны оставаться с ним синхронными. Если дизайнер правит v1 theme
— правим этот файл и прогоняем тесты.

Используется хост-слоем (``ui/shell/*``) и виджетами (``ui/widgets/*``).
Шаблоны (``ui/templates/*``) тоже могут его читать — токены намеренно
в ``ui/``, не в ``core/``, потому что они являются частью контракта
тулкита. Бэкенды (``sources/*``, ``mergers/*``, ``renderers/*``) его
импортировать **не должны** — это нарушение слоя.
"""

from __future__ import annotations

# ── Colors (Figma v1 theme.css) ────────────────────────────────────────
#: canvas / фон главного окна
COLOR_BACKGROUND = "#FAF8F5"
#: фон карточек, drawer'а, модальных окон
COLOR_CARD = "#FFFFFF"
#: основной текст
COLOR_FOREGROUND = "#2D2520"
#: вторичный текст, подписи, метки
COLOR_MUTED_FG = "#6B625A"
#: фон для hover/selected состояний (вторичная поверхность)
COLOR_SECONDARY = "#F5F2EF"
#: фон для disabled состояний
COLOR_MUTED = "#E8E4DF"
#: основной акцент (burnt ochre — brand-цвет)
COLOR_ACCENT = "#D4843B"
#: hover-вариант акцента (чуть темнее)
COLOR_ACCENT_HOVER = "#C27431"
#: текст на accent-фоне
COLOR_ACCENT_FG = "#FFFFFF"
#: цвет бордюров, разделителей
COLOR_BORDER = "rgba(107, 98, 90, 0.15)"
#: success (зелёный, «готов» / done-состояния)
COLOR_SUCCESS = "#5A8A3E"
#: полупрозрачный backdrop за drawer'ом (foreground @ 25% alpha)
COLOR_BACKDROP = "rgba(45, 37, 32, 0.25)"

# ── Radii / spacing ────────────────────────────────────────────────────
#: стандартный радиус для карточек и drawer'а
RADIUS_CARD_PX = 10
#: радиус для кнопок и чипов
RADIUS_BUTTON_PX = 8
#: радиус для мелких чипов-статусов
RADIUS_CHIP_PX = 6

#: padding для «контент» зон (карточка, drawer content)
PAD_CONTENT_PX = 24
#: padding для компактных зон (footer, header)
PAD_COMPACT_PX = 20
#: стандартный вертикальный gap между блоками
GAP_LARGE_PX = 20
#: gap между элементами внутри карточки
GAP_MEDIUM_PX = 16
#: gap для мелких элементов
GAP_SMALL_PX = 8

# ── Shadow (Qt не умеет CSS box-shadow — используем QGraphicsDropShadow)
#: RGBA компоненты для drop shadow карточек (107, 98, 90, 0.08)
SHADOW_CARD_RGBA = (107, 98, 90, 20)  # alpha 0.08 * 255 ≈ 20
SHADOW_CARD_BLUR_RADIUS = 8
SHADOW_CARD_OFFSET_Y = 2

# ── Typography (размеры в px для inline QSS) ───────────────────────────
FONT_SIZE_H1_PX = 22
FONT_SIZE_H2_PX = 18
FONT_SIZE_H3_PX = 16
FONT_SIZE_BODY_PX = 14
FONT_SIZE_SMALL_PX = 13
FONT_SIZE_MICRO_PX = 12
FONT_SIZE_TINY_PX = 11
