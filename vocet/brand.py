"""Vocet's brand in code: the design tokens, the logo, the tray and app icons.

Everything visual reads from here, so the pill (QPainter) and the window (QML) can't drift
apart. QML reads one flat dict, tokens(), published as the `theme` context property; Python
reads the same values through current() and color(). The logo is drawn, not loaded from image
files: three sound bars flowing into a text caret, so code is the simplest "source file".

Colours are "#RRGGBB", or "#AARRGGBB" when translucent (the format QML and QColor read), with
alpha rounded to the nearest byte.
"""

import functools
import math
import struct
from pathlib import Path

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from .settings import THEME_TO_ACCENT

# ------------------------------------------------------------------ colour (v4 "Calm glass")

# The window is pure black (dark) or pure white (light); Windows' light/dark picks one. Surfaces
# are neutral glass on it: translucent white on black, translucent black (or white cards) on
# white. Depth comes from a subtle rim and small soft shadows, never from colour: the accent is
# only for what you act on (the primary button, switches, today's bar, focus, the selected
# page's icon, links). Translucent fills are white (dark) or black (light) over whatever they
# sit on, so one token works on the window, a card or a menu.
# `selection` here is Violet's: tokens() derives it from the chosen accent.
APPEARANCE = {
    "dark": {
        "bgWindow": "#000000", "bgGroup": "#0B0B0C", "bgElevated": "#1C1C1E", "bgField": "#0D0D0E",
        "fillHover": "#0FFFFFFF", "fillPressed": "#17FFFFFF", "fillSelected": "#14FFFFFF",
        "fillControl": "#17FFFFFF", "fillControlHover": "#21FFFFFF", "fillControlPressed": "#0FFFFFFF",
        "fillThumb": "#2EFFFFFF", "separator": "#14FFFFFF", "strokeControl": "#1AFFFFFF",
        "strokeField": "#24FFFFFF", "strokeStrong": "#74747A",
        "textPrimary": "#F5F5F7", "textSecondary": "#A1A1A6", "textTertiary": "#8E8E93",
        "textDisabled": "#5E5E65", "selection": "#3A2F67",
        "success": "#32D74B", "warning": "#F5A83B", "danger": "#FF6159", "dangerText": "#FF7C73",
        "dangerFill": "#D8372E", "onDanger": "#FFFFFF",
        "scrim": "#80000000", "shadow1": "#80000000", "shadow2": "#B3000000",
        "pillBg": "#18181B", "pillStroke": "#1AFFFFFF",
    },
    "light": {
        "bgWindow": "#FFFFFF", "bgGroup": "#FFFFFF", "bgElevated": "#FFFFFF", "bgField": "#FFFFFF",
        "fillHover": "#08000000", "fillPressed": "#12000000", "fillSelected": "#0D000000",
        "fillControl": "#0D000000", "fillControlHover": "#14000000", "fillControlPressed": "#08000000",
        "fillThumb": "#FFFFFF",  # plus a rim and a small shadow, drawn by QML
        "separator": "#12000000", "strokeControl": "#1A000000", "strokeField": "#26000000",
        "strokeStrong": "#8A8A90",
        "textPrimary": "#1D1D1F", "textSecondary": "#636366", "textTertiary": "#6E6E73",
        "textDisabled": "#A3A3A9", "selection": "#DDD5FB",
        "success": "#1B8A4C", "warning": "#A35C00", "danger": "#D7362C", "dangerText": "#C0271F",
        "dangerFill": "#C8322A", "onDanger": "#FFFFFF",
        "scrim": "#33000000", "shadow1": "#1F000000", "shadow2": "#2E000000",
        "pillBg": "#18181B", "pillStroke": "#1AFFFFFF",  # the pill stays dark in light mode
    },
}

# The glass (v4, level A "Calm" of the prototype): what ui/components/GlassShape.qml paints.
# Functional glass (the sidebar pane, controls) and content cards are two materials; cards are
# quieter. Numbers are px (blur, offsets) or 0-1 strengths.
GLASS = {
    "dark": {
        "glassTop": "#14FFFFFF", "glassBottom": "#06FFFFFF", "sheen": "#08FFFFFF", "spec": "#08FFFFFF",
        "rimTop": "#36FFFFFF", "rimMid": "#0AFFFFFF", "rimBottom": "#17FFFFFF",
        "glassShadow": "#80000000", "shadowSoft": "#66000000",
        "cardTop": "#0DFFFFFF", "cardBottom": "#08FFFFFF", "cardRimTop": "#21FFFFFF", "cardRimMid": "#00FFFFFF",
        "cardRimBottom": "#0DFFFFFF", "cardRimSlice": "#0AFFFFFF",
        "controlTop": "#1FFFFFFF", "controlBottom": "#12FFFFFF", "controlHover": "#12FFFFFF",
        "controlPressed": "#14000000", "fieldFill": "#0DFFFFFF", "fieldRim": "#1FFFFFFF",
        "segThumbTop": "#2EFFFFFF", "segThumbBottom": "#1FFFFFFF", "track": "#1FFFFFFF", "thumb": "#FFFFFF",
        "navSelTop": "#17FFFFFF", "navSelBottom": "#12FFFFFF", "navSelRim": "#0FFFFFFF",
        "tileFill": "#17FFFFFF", "chipFill": "#17FFFFFF", "bar": "#FFFFFF", "barA": 0.14,
        "btnSheen": 0.07, "btnRimTop": "#4DFFFFFF", "btnRimBottom": "#1FFFFFFF", "btnHover": 0.06,
        "sideShadowBlur": 20, "sideShadowY": 6, "ctrlShadowBlur": 8, "ctrlShadowY": 2,
        "cardShadowBlur": 16, "cardShadowY": 4, "cardRimDiag": 0.4,
    },
    "light": {
        "glassTop": "#06000000", "glassBottom": "#0A000000", "sheen": "#80FFFFFF", "spec": "#40FFFFFF",
        "rimTop": "#FFFFFFFF", "rimMid": "#0A000000", "rimBottom": "#14000000",
        "glassShadow": "#12000000", "shadowSoft": "#0D000000",
        "cardTop": "#FFFFFFFF", "cardBottom": "#FFFFFFFF", "cardRimTop": "#12000000", "cardRimMid": "#12000000",
        "cardRimBottom": "#17000000", "cardRimSlice": "#12000000",
        "controlTop": "#FFFFFFFF", "controlBottom": "#FAFFFFFF", "controlHover": "#08000000",
        "controlPressed": "#12000000", "fieldFill": "#08000000", "fieldRim": "#1A000000",
        "segThumbTop": "#FFFFFFFF", "segThumbBottom": "#FFFFFFFF", "track": "#1A000000", "thumb": "#FFFFFF",
        "navSelTop": "#0D000000", "navSelBottom": "#0D000000", "navSelRim": "#0F000000",
        "tileFill": "#0D000000", "chipFill": "#0D000000", "bar": "#000000", "barA": 0.08,
        "btnSheen": 0.07, "btnRimTop": "#40FFFFFF", "btnRimBottom": "#14FFFFFF", "btnHover": 0.06,
        "sideShadowBlur": 14, "sideShadowY": 4, "ctrlShadowBlur": 8, "ctrlShadowY": 2,
        "cardShadowBlur": 16, "cardShadowY": 4, "cardRimDiag": 0.0,
    },
}

# The 1 px border DWM draws round the window: quiet, so the black (or white) window keeps its
# edge on any wallpaper. Opaque, because DWM has no alpha.
WINDOW_BORDER = {"dark": "#2B2B2E", "light": "#D6D6D8"}
# The app icon's tile keeps its charcoal (the window's black would vanish on a dark taskbar).
ICON_TILE = "#1C1C1F"

# ------------------------------------------------------------------ accents

# One accent, one job: what you can act on, what's on, and your live voice. Violet is the
# default again; Black & white (mono), blue, teal and pink stay as choices. `accent` is
# the flat fill (the switch, dots); accentTop/accentBottom are the primary button's gradient
# (derived from `accent` when an accent doesn't set them), and its label reads at >= 4.5:1 on
# `accent`. onAccent is per accent because Mono's dark fill is near-white and needs a dark
# label. `focus`: the keyboard focus ring (derived: accentText in dark, accent in light).
ACCENTS = {
    "violet": {"label": "Violet",
               "dark": {"accent": "#6B48F4", "accentHover": "#7552F5", "accentPressed": "#5C38EA",
                        "accentTop": "#7A5AFC", "accentBottom": "#5C35EC", "focus": "#9B80FF",
                        "accentText": "#A993FF", "onAccent": "#FFFFFF"},
               "light": {"accent": "#6843F2", "accentHover": "#7250F4", "accentPressed": "#5A34E0",
                         "accentTop": "#7F5CFF", "accentBottom": "#5A34E8", "focus": "#6A45F5",
                         "accentText": "#5A34E0", "onAccent": "#FFFFFF"}},
    "mono": {"label": "Black & white",
             "dark": {"accent": "#F0F0F3", "accentHover": "#FFFFFF", "accentPressed": "#D1D1D6",
                      "accentTop": "#FFFFFF", "accentBottom": "#E3E3E8", "focus": "#FFFFFF",
                      "accentText": "#F5F5F7", "onAccent": "#000000", "selection": "#4B4B50"},
             "light": {"accent": "#161618", "accentHover": "#2C2C2E", "accentPressed": "#000000",
                       "accentTop": "#2C2C2E", "accentBottom": "#000000", "focus": "#000000",
                       "accentText": "#1D1D1F", "onAccent": "#FFFFFF", "selection": "#D6D6DB"}},
    "blue": {"label": "Blue",
             "dark": {"accent": "#246EEF", "accentHover": "#2467DC", "accentPressed": "#1D5BCB",
                      "accentText": "#6FA0F5", "onAccent": "#FFFFFF"},
             "light": {"accent": "#1259D8", "accentHover": "#2A6ADC", "accentPressed": "#0E4AB8",
                       "accentText": "#1259D8", "onAccent": "#FFFFFF"}},
    "teal": {"label": "Teal",
             "dark": {"accent": "#0C818E", "accentHover": "#0F7884", "accentPressed": "#0A6C77",
                      "accentText": "#22B3C3", "onAccent": "#FFFFFF"},
             # accentText a shade under the fill: at #0B717D the logo's 70 % bar is 2.98:1 on the window
             "light": {"accent": "#0B717D", "accentHover": "#237F8A", "accentPressed": "#085D67",
                       "accentText": "#0B6F7B", "onAccent": "#FFFFFF"}},
    "pink": {"label": "Pink",
             "dark": {"accent": "#D5317D", "accentHover": "#C43075", "accentPressed": "#B72869",
                      "accentText": "#EC7DB1", "onAccent": "#FFFFFF"},
             "light": {"accent": "#BD276D", "accentHover": "#C43D7C", "accentPressed": "#9F1F5B",
                       "accentText": "#BD276D", "onAccent": "#FFFFFF"}},
}
DEFAULT_ACCENT = "violet"
# Selected text sits on the accent at 35 % over the field (22 % in light). An accent can set its
# own: 35 % white would put a bright block behind Mono's selected text.
SELECTION_MIX = {"dark": 0.35, "light": 0.22}
# The logo's three bars, short to tall (Logo.qml, OpeningMark.qml, the app icon), per appearance.
# On black the full accent at 70 % read as muddy (2.2:1 for violet on the pane), so dark lifts the
# two short bars; the three steps stay visible. (Logos are exempt from WCAG 1.4.11; the short bar
# just shouldn't disappear.)
LOGO_OPACITY = {"dark": (0.80, 0.90, 1.00), "light": (0.70, 0.85, 1.00)}

# ------------------------------------------------------------------ type, space, shape, motion


def family_for(px: int) -> str:
    """Segoe UI Variable's optical size for a pixel size, as in Windows 11's type ramp."""
    return "Segoe UI Variable " + ("Display" if px >= 20 else "Text" if px >= 13 else "Small")


# Apple's macOS text styles raised 1-2 px, because Segoe's x-height is smaller than SF's:
# (px, line height, weight) at 100 % text size. Regular and Semibold only.
_RAMP = {
    "display": (44, 52, 600), "largeTitle": (30, 36, 600), "title1": (22, 28, 600), "title2": (18, 24, 600), "title3": (16, 22, 600),
    "headline": (14, 20, 600), "body": (14, 20, 400), "callout": (13, 18, 400), "subheadline": (12, 16, 400),
    "footnote": (12, 16, 400), "caption1": (11, 14, 400), "caption2": (11, 14, 600),
}
TYPE = {name: (family_for(px), px, line, weight) for name, (px, line, weight) in _RAMP.items()}

SPACE = (2, 4, 8, 12, 16, 20, 24, 32, 40, 48)  # space1..space10: a 4 px grid
# v4: cards 18, the sidebar pane 22, buttons, switches, segments and nav items are capsules
# (radius = height / 2, drawn by QML), fields and pop-ups 10.
RADIUS = {"radiusCard": 18, "radiusPane": 22, "radiusField": 10, "radiusGroup": 18, "radiusControl": 10,
          "radiusThumb": 8, "radiusMenu": 12, "radiusMenuItem": 8, "radiusSidebarItem": 20, "radiusTooltip": 8,
          "radiusKeycap": 7, "radiusToast": 20, "radiusDialog": 18}
# ms. Everything eases out (OutCubic) unless noted; nothing loops. Page: a new page fades in and
# rises `risePage` px. Glide: the sidebar's selection and the segmented thumb move between items.
# Reveal: cards and rows fade in and rise `riseItem` px once when a page opens, `motionStagger`
# apart (at most 6 staggered). Number: a count ticking to its new value.
MOTION = {"motionFast": 100, "motionBase": 150, "motionMedium": 200, "motionHandoff": 240,
          "motionPage": 240, "motionGlide": 260, "motionReveal": 300, "motionStagger": 35, "motionNumber": 600,
          "risePage": 8, "riseItem": 10}
EASE_EMPHASIZED = (0.2, 0.0, 0.0, 1.0, 1.0, 1.0)  # QML Easing.BezierSpline; signature moments only

# ------------------------------------------------------------------ v2 compatibility

# The v2 colour themes. The old Settings picker still lists them; each now picks the accent that
# replaced it (settings.THEME_TO_ACCENT). Their keys (base, glass, specA...) stay published with
# v2 values until the old QML pages are gone. Where v2 and v3 share a name (textPrimary,
# strokeStrong, success...), v3 wins.
THEMES = {
    "violet": {"label": "Violet", "spectrum": ("#EFE9FF", "#CDBBFF", "#A98BFF", "#8A6CF4"),
               "aurora": 0.45},
    "graphite": {"label": "Graphite", "spectrum": ("#F4F5F8", "#D9DCE3", "#BFC3CC", "#A6ABB6"),
                 "aurora": 0.0},
    "ocean": {"label": "Ocean", "spectrum": ("#C9F4FF", "#86DAF7", "#5AAEF5", "#4F7FF0"),
              "aurora": 0.4},
    "forest": {"label": "Forest", "spectrum": ("#E2FAD0", "#A6EDC0", "#65D6AA", "#3AB792"),
               "aurora": 0.35},
    "aurora": {"label": "Aurora", "spectrum": ("#6CF0D2", "#78A8FF", "#A98BFF", "#FF8AC8"),
               "aurora": 1.0},
}
_V2 = {
    "base": "#06060A", "sidebar": "#08FFFFFF", "glass": "#0BFFFFFF", "glassHover": "#13FFFFFF",
    "glassSelected": "#1CFFFFFF", "stroke": "#16FFFFFF", "highlight": "#24FFFFFF",
    "raised": "#111115", "hover": "#19191C", "selected": "#212125", "popup": "#15151B", "pill": "#0B0B11",
    "error": "#FF8A8A",
}
_V2_THEME_OF = {"mono": "graphite", "violet": "violet", "blue": "ocean", "teal": "forest"}
_V2_PINK = {"spectrum": ("#FFE3F0", "#F7B2D2", "#EC7DB1", "#D5317D"), "aurora": 0.4}  # Pink is new in v3, so it gets a v2-style theme of its own


def _v2_theme(accent: str) -> dict:
    return THEMES[_V2_THEME_OF[accent]] if accent in _V2_THEME_OF else _V2_PINK


def _v2_tokens(accent: str) -> dict:
    t = _v2_theme(accent)
    s = t["spectrum"]
    return {**_V2, "specA": s[0], "specB": s[1], "specC": s[2], "specD": s[3],
            "aurora": t["aurora"], "glow": s[1], "themeName": _V2_THEME_OF.get(accent, accent)}


# ------------------------------------------------------------------ the flat dict for QML


def mix(fg: str, alpha: float, bg: str) -> str:
    """fg at `alpha` over bg, as the opaque '#RRGGBB' you'd see (both inputs opaque)."""
    f, b = QColor(fg), QColor(bg)
    ch = lambda x, y: round(x * alpha + y * (1 - alpha))
    return "#%02X%02X%02X" % (ch(f.red(), b.red()), ch(f.green(), b.green()), ch(f.blue(), b.blue()))


def _round(x: float) -> int:
    return int(math.floor(x + 0.5))  # half up: 16.5 px is 17 (round() would pick the even 16)


def tokens(mode: str, accent: str, text_scale: float = 1.0, palette: dict | None = None) -> dict:
    """The flat dict QML reads as `theme`: colours for the mode and accent, the type ramp times
    text_scale (Windows' Text size, 1.0-2.25), spacing, radii and motion.

    `palette`: a Windows contrast theme's system colours (window.system_palette()). They replace
    the main colours, because a contrast theme must win over the brand.
    """
    mode = mode if mode in APPEARANCE else "dark"
    accent = accent if accent in ACCENTS else DEFAULT_ACCENT
    t = dict(_tokens(mode, accent, float(text_scale), tuple(sorted(palette.items())) if palette else None))
    t["easeEmphasized"] = list(EASE_EMPHASIZED)  # a fresh list, so callers can't change the cached one
    return t


@functools.lru_cache(maxsize=64)
def _tokens(mode: str, accent: str, text_scale: float, palette: tuple | None) -> dict:
    t = _v2_tokens(accent)  # first, so v3 names win where they overlap
    t.update(APPEARANCE[mode])
    t.update(GLASS[mode])
    a = ACCENTS[accent][mode]
    t.update(a)
    if "selection" not in a:
        t["selection"] = mix(a["accent"], SELECTION_MIX[mode], t["bgField"])
    t.setdefault("accentTop", mix("#FFFFFF", 0.06, a["accent"]))
    t.setdefault("accentBottom", mix("#000000", 0.08, a["accent"]))
    t.setdefault("focus", a["accentText"] if mode == "dark" else a["accent"])
    t["switchOnThumb"] = a["onAccent"]
    t["logoBarA1"], t["logoBarA2"], t["logoBarA3"] = LOGO_OPACITY[mode]
    t["onSelection"] = t["textPrimary"]
    for name, (_family, px, line, weight) in TYPE.items():
        size = _round(px * text_scale)
        t[name + "Size"], t[name + "Line"] = size, _round(line * text_scale)
        t[name + "Weight"], t[name + "Family"] = weight, family_for(size)  # optical size follows the real size
    t["textScale"] = text_scale
    t.update({f"space{i}": v for i, v in enumerate(SPACE, 1)})
    t.update(RADIUS)
    t.update(MOTION)
    t.update(mode=mode, accentName=accent, highContrast=palette is not None)
    if palette:
        t.update(_contrast_theme(dict(palette)))
    return t


def _contrast_theme(pal: dict) -> dict:
    """A Windows contrast theme: the system's colours replace the main tokens.

    Best effort. Fills go flat, so text only ever sits on a colour the theme chose, and strokes
    carry the shapes; QML should outline selected items when theme.highContrast is true. Signal
    colours stay, since they're icons next to words. The pill keeps its own dark palette.
    """
    window, text, flat, pick = pal["window"], pal["windowText"], "#00000000", pal["highlight"]
    t = dict.fromkeys(("bgWindow", "bgGroup", "bgElevated"), window)
    t.update(dict.fromkeys(("fillHover", "fillPressed", "fillSelected", "fillControl", "fillControlHover",
                            "fillControlPressed", "fillThumb"), flat))
    t.update(dict.fromkeys(("separator", "strokeControl", "strokeField", "strokeStrong", "textPrimary",
                            "textSecondary", "textTertiary", "dangerText"), text))
    t.update(dict.fromkeys(("accent", "accentHover", "accentPressed", "selection", "dangerFill"), pick))
    t.update(dict.fromkeys(("onAccent", "onSelection", "onDanger"), pal["highlightedText"]))
    t.update(bgField=pal["base"], textDisabled=pal["grayText"], accentText=pal["link"])
    # Glass goes flat: fills take the window colour, rims become the text colour (so every
    # surface still has an edge), shadows, sheens and tints vanish.
    t.update(dict.fromkeys(("glassTop", "glassBottom", "cardTop", "cardBottom", "controlTop", "controlBottom",
                            "segThumbTop", "segThumbBottom", "navSelTop", "navSelBottom", "fieldFill", "track",
                            "tileFill", "chipFill"), window))
    t.update(dict.fromkeys(("rimTop", "rimMid", "rimBottom", "cardRimTop", "cardRimMid", "cardRimBottom",
                            "cardRimSlice", "fieldRim", "navSelRim", "btnRimTop", "btnRimBottom"), text))
    t.update(dict.fromkeys(("sheen", "spec", "glassShadow", "shadowSoft", "controlHover", "controlPressed"), flat))
    t.update(accentTop=pick, accentBottom=pick, focus=text, thumb=text, bar=text, switchOnThumb=pal["highlightedText"],
             btnSheen=0.0, btnHover=0.0)
    return t


# ------------------------------------------------------------------ the current tokens

_state = {"mode": "dark", "accent": DEFAULT_ACCENT, "text_scale": 1.0, "palette": None}
TOKENS: dict = {}  # the current flat dict, updated in place (older code reads brand.TOKENS directly)


def apply(mode: str | None = None, accent: str | None = None, text_scale: float | None = None,
          palette=...) -> dict:
    """Makes these the current tokens. None (or ... for palette) keeps the current value, so
    the accent and the Windows settings can change independently. Returns current()."""
    if mode is not None:
        _state["mode"] = mode if mode in APPEARANCE else "dark"
    if accent is not None:
        _state["accent"] = accent if accent in ACCENTS else DEFAULT_ACCENT
    if text_scale is not None:
        _state["text_scale"] = float(text_scale)
    if palette is not ...:
        _state["palette"] = palette or None
    TOKENS.clear()
    TOKENS.update(tokens(**_state))
    return current()


def current() -> dict:
    """A copy of the current flat dict: what QML sees as `theme`."""
    return dict(TOKENS)


def color(name: str, alpha: float = 1.0) -> QColor:
    c = QColor(TOKENS[name])
    c.setAlphaF(c.alphaF() * alpha)
    return c


def accent_for(name: str) -> str:
    """The accent for a v2 theme name (ocean -> blue...) or an accent name. Unknown -> the default."""
    return THEME_TO_ACCENT.get(name) or (name if name in ACCENTS else DEFAULT_ACCENT)


def apply_theme(name: str) -> str:
    """v2 entry point, kept while callers migrate: a theme (or accent) name picks its accent.
    Returns the accent used."""
    accent = accent_for(name)
    apply(accent=accent)
    return accent


def spectrum() -> tuple:
    """The v2 voice spectrum closest to the current accent (for the v2 pill while it migrates)."""
    return _v2_theme(_state["accent"])["spectrum"]


apply()  # the defaults, so importing brand is enough to draw

# ------------------------------------------------------------------ the glyph

# Three sound bars flowing into a text caret (an I-beam); the last element is the caret.
HEIGHTS = (0.34, 0.54, 0.76, 1.00)
OPACITY = (0.70, 0.85, 1.00, 1.00)  # the bars, short to tall, in one accent


def spectrum_at(t: float, stops=None) -> QColor:
    """Colour at position t (0..1) along the voice spectrum (or `stops`), interpolated."""
    stops = stops or spectrum()
    t = min(1.0, max(0.0, t)) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    a, b, f = QColor(stops[i]), QColor(stops[i + 1]), t - i
    return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * f,
                           a.greenF() + (b.greenF() - a.greenF()) * f,
                           a.blueF() + (b.blueF() - a.blueF()) * f)


def paint_caret(p: QPainter, cx: float, cy: float, height: float, stroke: float, ink: QColor,
                serifs: bool = True) -> None:
    """A text cursor: a thin vertical stroke with small top/bottom serifs (I-beam)."""
    p.setPen(Qt.NoPen)
    p.setBrush(ink)
    p.drawRoundedRect(QRectF(cx - stroke / 2, cy - height / 2, stroke, height), stroke / 2, stroke / 2)
    if serifs:
        w = stroke * 3.2
        for y in (cy - height / 2, cy + height / 2 - stroke):
            p.drawRoundedRect(QRectF(cx - w / 2, y, w, stroke), stroke / 2, stroke / 2)


def paint_glyph(p: QPainter, rect: QRectF, ink: QColor | None = None, heights=None, opacity=None,
                serifs: bool = True, stops=None, bars: QColor | None = None, caret: QColor | None = None) -> None:
    """Draws the glyph centred in rect: the sound bars, then the caret.

    `ink` draws it all in one colour (mono). Otherwise the bars are `bars` (default: the current
    accent), or a gradient along `stops` (v2), and the caret is
    `caret` (default: textPrimary). `opacity` fades each element, 70/85/100 % by default.
    """
    heights = heights or HEIGHTS
    opacity = opacity or OPACITY
    n = len(heights)
    bar_ink = QColor(bars) if bars is not None else color("accent")
    caret_ink = QColor(caret) if caret is not None else color("textPrimary")
    bar_w = rect.width() / (n - 1 + (n - 1) * 0.85 + 0.9)  # bars + gaps + caret slot
    gap = bar_w * 0.85
    p.save()
    p.setPen(Qt.NoPen)
    for i, (h, a) in enumerate(zip(heights, opacity)):
        if ink is not None:
            c = QColor(ink)
        elif i == n - 1:
            c = QColor(caret_ink)
        elif stops is not None:
            c = spectrum_at(i / max(1, n - 2), stops)
        else:
            c = QColor(bar_ink)
        c.setAlphaF(c.alphaF() * a)
        bh = max(bar_w, rect.height() * h)
        x = rect.left() + i * (bar_w + gap)
        if i < n - 1:
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x, rect.center().y() - bh / 2, bar_w, bh), bar_w / 2, bar_w / 2)
        else:
            paint_caret(p, x + bar_w * 0.45, rect.center().y(), bh, bar_w * 0.52, c, serifs)
    p.restore()


# ------------------------------------------------------------------ app and tray icons


def paint_app_icon(p: QPainter, size: float, accent: str | None = None) -> None:
    """A solid charcoal tile with the two-tone glyph. No gradient, light leaks or edge
    highlight (no baked-in glows). Always the dark palette, like the tile."""
    t = tokens("dark", accent or _state["accent"])
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(0, 0, size, size).adjusted(size * 0.04, size * 0.04, -size * 0.04, -size * 0.04)
    radius = r.width() * 0.26
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(ICON_TILE))
    p.drawRoundedRect(r, radius, radius)
    glyph = QRectF(0, 0, r.width() * 0.54, r.height() * 0.50)
    glyph.moveCenter(r.center())
    paint_glyph(p, glyph, bars=QColor(t["accent"]), caret=QColor(t["textPrimary"]),  # the full violet, as in Logo.qml
                opacity=LOGO_OPACITY["dark"] + (1.0,))


def app_icon_image(size: int, accent: str | None = None) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    paint_app_icon(p, size, accent)
    p.end()
    return img


def tray_image(state: str, size: int, light_taskbar: bool = False) -> QImage:
    """The tray glyph at one size. state: ready | listening | paused | loading.

    At rest it's mono, like the system's own tray icons. While listening, the bars grow and take
    the accent (the variant made for the taskbar's light or dark), so the change is in shape as
    well as colour. Paused and loading are dimmed to 45 %.
    """
    t = tokens("light" if light_taskbar else "dark", _state["accent"])
    ink = QColor(t["textPrimary"])
    if state in ("paused", "loading"):
        ink.setAlphaF(0.45)
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    glyph = QRectF(0, 0, size * 0.74, size * 0.78)
    glyph.moveCenter(QRectF(0, 0, size, size).center())
    heights = (0.62, 0.86, 1.0) if state == "listening" else (0.44, 0.70, 1.0)
    paint_glyph(p, glyph, None if state == "listening" else ink, heights=heights,
                opacity=(0.7, 0.88, 1.0), serifs=size >= 24,
                bars=QColor(t["accentText"]), caret=ink)
    p.end()
    return img


def tray_icon(state: str = "ready", light_taskbar: bool = False) -> QIcon:
    """Glyph only, like other tray icons (see tray_image), at every size the taskbar asks for."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48):
        icon.addPixmap(QPixmap.fromImage(tray_image(state, size, light_taskbar)))
    return icon


def window_icon(accent: str | None = None) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(app_icon_image(size, accent)))
    return icon


def write_ico(path: Path, sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256), accent: str | None = None) -> None:
    """Multi-resolution .ico (PNG-compressed entries), so shortcuts are crisp at every size.

    Qt's ICO writer only stores one image, so the ~15-line ICO container is written by hand:
    a 6-byte header, one 16-byte entry per image, then the PNG data.
    """
    pngs = []
    for s in sizes:
        buf = QByteArray()
        dev = QBuffer(buf)
        dev.open(QIODevice.WriteOnly)
        app_icon_image(s, accent).save(dev, "PNG")
        pngs.append((s, bytes(buf)))
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for s, data in pngs:
        dim = 0 if s >= 256 else s  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    Path(path).write_bytes(header + entries + blobs)


def write_noise(path: Path, size: int = 160) -> Path:
    """A tile of fine film grain (v2). Laid over the window at ~4 % it removes gradient banding."""
    if not Path(path).exists():
        rng = np.random.default_rng(7)
        grain = (rng.random((size, size)) * 255).astype(np.uint8)
        img = QImage(size, size, QImage.Format_ARGB32)
        for y in range(size):
            for x in range(size):
                v = int(grain[y, x])
                img.setPixelColor(x, y, QColor(v, v, v, 255))
        img.save(str(path))
    return Path(path)


def taskbar_is_light() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False
