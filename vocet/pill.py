"""The floating pill: Vocet's main UI (the design system's "pill").

    hidden      nothing on screen, not even a window (the default while idle)
    idle        a small dark capsule at the bottom of the screen (Settings: show the bar when idle)
    starting    the keys are pressed and the microphone is still opening: the listening
                capsule with its 19 bars at rest, as dim white dots. Not the accent yet, because
                the accent means your voice and nothing is being heard. Still: no spinner, no motion
    listening   the capsule opens and 19 bars in the accent colour follow your voice, radiating out
                from the middle. Hands-free adds a small stop mark ("tap to finish"). From
                starting, the dots crossfade into the accent: that (and the start sound) is "talk now"
    processing  the bars settle into dots, and a gentle opacity wave runs from the centre out
    done        THE SIGNATURE, the caret signature: the dots gather into a white text caret, the logo's
                three bars step out to its left (for a beat the pill *is* the logo), then it fades
                and the window goes away
    message     a short notice: a warning glyph for failures, an info glyph for neutral notices
    loading     a notice with a small ring spinner

Restraint: one accent, and it means your voice. The capsule is flat, opaque and always dark, so it
reads over a white document as well as over a dark desktop. A hairline edge and a neutral shadow
set it off. No glows, gradients or light effects.

How it stays smooth and cheap:
- The window never resizes. It's a fixed transparent canvas, and the capsule is drawn inside it
  with animated size/opacity. Resizing a real window every frame is what makes overlays stutter.
- Sizes ease towards their target with exponential smoothing (a critically damped spring, no
  overshoot), so interrupted animations stay fluid. Pressing the key mid-animation just
  retargets; nothing ever waits for an animation to finish.
- The 60 fps timer only runs while something moves. Idle, or a message that has faded in, means
  no repaints and 0 % CPU.
- Edges land on whole device pixels (capsule, hairline, bars, caret), so it stays crisp at every
  display scale.
- Reduced motion (Windows "Animation effects" off): sizes snap, content crossfades over 120 ms,
  the processing dots hold at 60 %, and "done" shows the finished logo for 400 ms. The live level
  bars stay, because they're information.

It never takes keyboard focus and ignores the mouse: clicks pass straight through.

Staying centred: every time the pill appears, it asks Windows (not Qt) where its window
really is. After the display sleeps, Windows briefly swaps your monitor for a 100 % "lock
screen" display, and Qt could come back believing the pill was still at 100 % on a 200 %
screen: half size, in the left middle of the screen. If the check fails, the window is
rebuilt; a fresh window takes the display's real scale. Display changes are logged.
"""

import ctypes
import logging
import math
import time
from ctypes import wintypes

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import brand

log = logging.getLogger("vocet.pill")

CANVAS_W, CANVAS_H = 480, 150
BOTTOM_OFFSET = 36          # px between the pill's centre and the bottom of the work area
PILL_H, LISTEN_W, LOCKED_W, DONE_W = 36, 164, 188, 56  # hands-free is wider: room for the stop mark
BARS, BAR_W, BAR_GAP = 19, 3.0, 3.5
CENTER = BARS // 2
BAR_MIN, BAR_MAX = 3.0, 20.0  # a silent bar is a dot
WAVE_S, WAVE_DOTS, DOT_FLOOR = 0.7, 12, 0.6  # processing: wave period, wavelength in dots, dimmest opacity
CARET_H, CARET_W = 20.0, 2.5
CARET_DX = 8                # the caret sits right of centre, so caret + logo bars are centred together
LOGO = ((15, 1.0), (11, 0.85), (7, 0.7))  # the logo's bars from the caret outwards: height, opacity
LOGO_STEP = 6.0             # each logo bar steps out this far from the one before it
LOGO_GAP = 6.5              # caret to the tallest bar, centre to centre: clear of the caret's serifs
DONE_HOLD_MS = 720          # the whole caret signature, its fade included; then the window goes
FADE_S = 0.12               # reduced motion: every change is a 120 ms crossfade
STARTING_A = 0.35           # starting: the resting dots, white at this opacity (the mic isn't on yet)
SHADOW_Y, SHADOW_BLUR, SHADOW_A = 4.0, 16.0, 0.30
GLYPH, GAP, PAD = 16, 8, 14  # message: glyph, glyph-to-text gap, side padding (capsule = text + 52)
MAX_W = CANVAS_W - 32       # the widest capsule that still leaves room for its shadow

SHAPES = {  # width, height, capsule opacity
    "hidden": (40, 6, 0.0),
    "idle": (40, 6, 0.6),
    "starting": (LISTEN_W, PILL_H, 1.0),
    "listening": (LISTEN_W, PILL_H, 1.0),
    "processing": (LISTEN_W, PILL_H, 1.0),
    "done": (DONE_W, PILL_H, 1.0),
}

WARNING_GLYPH, INFO_GLYPH = "", ""  # Segoe Fluent Icons
# set_mode(..., kind=) says which glyph a message gets: "warning" (amber, "something went wrong", the
# default) or "notice" (the neutral info glyph). The caller decides; the text is never inspected.
MESSAGE_KINDS = ("warning", "notice")


_user32 = ctypes.WinDLL("user32")
GWL_EXSTYLE, MONITOR_DEFAULTTONEAREST = -20, 2
WS_EX_NOACTIVATE, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = 0x08000000, 0x20, 0x80


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetDpiForWindow.argtypes = [wintypes.HWND]
_user32.GetDpiForWindow.restype = wintypes.UINT
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HMONITOR
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)]
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t


def reduced_motion() -> bool:
    """Windows Settings > Accessibility > Visual effects > Animation effects."""
    enabled = ctypes.c_bool(True)
    ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)  # SPI_GETCLIENTAREAANIMATION
    return not enabled.value


def placement_problem(window: tuple, work: tuple, dpi: int) -> str:
    """"" if the pill's window (left, top, right, bottom, in physical pixels) has the right size
    for the display's scale and sits at the bottom centre of the work area. Otherwise what's wrong."""
    scale = dpi / 96
    left, top, right, bottom = window
    want_w, want_h = CANVAS_W * scale, CANVAS_H * scale
    want_x, want_y = (work[0] + work[2]) / 2, work[3] - BOTTOM_OFFSET * scale
    slack = 2 + scale  # rounding at scales like 125 % and 150 %
    if (abs(right - left - want_w) <= slack and abs(bottom - top - want_h) <= slack
            and abs((left + right) / 2 - want_x) <= slack and abs((top + bottom) / 2 - want_y) <= slack):
        return ""
    return (f"{right - left}x{bottom - top} px centred at {(left + right) / 2:.0f},{(top + bottom) / 2:.0f}, "
            f"not {want_w:.0f}x{want_h:.0f} at {want_x:.0f},{want_y:.0f} ({scale:.0%} display)")


def describe_screens() -> str:
    return ", ".join(f"{s.name()} {s.geometry().width()}x{s.geometry().height()} at {s.devicePixelRatio():.0%}"
                     for s in QGuiApplication.screens())


def level_to_unit(rms: float) -> float:
    """Microphone RMS (0..1) -> bar height (0..1), on a dB scale like our ears."""
    db = 20 * math.log10(max(rms, 1e-6))
    return min(1.0, max(0.0, (db + 54) / 36))


def _smooth(current: float, target: float, dt: float, tau: float) -> float:
    return current + (target - current) * (1 - math.exp(-dt / tau))


def _ramp(current: float, target: float, dt: float, duration: float) -> float:
    """A linear fade: moves towards target by dt/duration per call (reduced motion's crossfades)."""
    step = dt / duration
    return target if abs(target - current) <= step else current + math.copysign(step, target - current)


def _clamp(t: float) -> float:
    return min(1.0, max(0.0, t))


def _ease_out(t: float) -> float:  # OutCubic
    return 1 - (1 - _clamp(t)) ** 3


def _ease_in(t: float) -> float:   # InCubic
    return _clamp(t) ** 3


def _emphasized(t: float) -> float:
    """easeEmphasized, the cubic Bézier in brand.EASE_EMPHASIZED (0.2, 0, 0, 1): signature moments only."""
    x1, y1, x2, y2 = brand.EASE_EMPHASIZED[:4]
    bezier = lambda u, a, b: 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u ** 2 * b + u ** 3
    t, lo, hi = _clamp(t), 0.0, 1.0
    for _ in range(20):  # solve x(u) = t by bisection (x rises monotonically)
        u = (lo + hi) / 2
        lo, hi = (u, hi) if bezier(u, x1, x2) < t else (lo, u)
    return bezier((lo + hi) / 2, y1, y2)


def _envelope(i: int) -> float:
    """Centre-weighted: the middle bars can reach full height, the outermost 30 % of it."""
    return 0.3 + 0.7 * math.cos((i - CENTER) / CENTER * math.pi / 2)


def _snap(v: float, dpr: float) -> float:
    """A logical coordinate rounded to the nearest device pixel."""
    return math.floor(v * dpr + 0.5) / dpr


def _alpha(color: QColor, alpha: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(c.alphaF() * _clamp(alpha))
    return c


def _bar(p: QPainter, x: float, cy: float, h: float, ink: QColor, alpha: float, dpr: float) -> None:
    """A round-ended bar centred on (x, cy). Its sides sit on device pixels, so it stays crisp."""
    if alpha < 0.004:
        return
    w = max(1, math.floor(BAR_W * dpr + 0.5)) / dpr
    p.setBrush(_alpha(ink, alpha))
    p.drawRoundedRect(QRectF(_snap(x - w / 2, dpr), cy - max(h, w) / 2, w, max(h, w)), w / 2, w / 2)


def _blurred(d: float, r: float, sigma: float) -> float:
    """How much of a band 2r wide, blurred by a Gaussian (sigma), covers a point d from its middle."""
    k = sigma * math.sqrt(2)
    return 0.5 * (math.erf((r - d) / k) + math.erf((r + d) / k))


class Pill(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(CANVAS_W, CANVAS_H)

        self._font = QFont()  # callout, 13 px Semibold. Asking for "Segoe UI Variable Text" + DemiBold gets Bold
        self._font.setFamilies(["Segoe UI Variable Text Semibold", "Segoe UI"])
        self._font.setPixelSize(13)
        self._font.setWeight(QFont.DemiBold)
        self._icons = QFont()
        self._icons.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
        self._icons.setPixelSize(GLYPH)
        self.reduced = reduced_motion()
        self.show_idle = False
        self.live = False                       # start() makes it show itself; previews never do
        self.locked = False                     # hands-free: shows a small stop mark ("tap to finish")
        self.mode, self.message = "hidden", ""
        self._text, self._text_w, self._notice = "", 0.0, False
        self.w, self.h, self.bg_a = 40.0, 6.0, 0.0
        self.content_a = 1.0                    # opacity of what's in the capsule (fades in after a change)
        self._old, self._old_a = None, 0.0      # what was in it before, fading out: a crossfade
        self._target = SHAPES["hidden"]
        self._bars = [0.0] * BARS               # bar heights, 0 (a dot) .. 1 (tallest)
        self._bar_a = [1.0] * BARS              # bar opacity: the processing wave
        self._history = [0.0] * BARS            # level history, newest in the middle
        self._lock_x = self._lock_a = 0.0       # hands-free: the bars make room (x), the stop mark fades in (a)
        self.level_source = None                # callable -> current mic RMS
        self._level = 0.0
        self._t = self._phase = 0.0             # seconds in this mode; a free-running clock (spinner)
        self._hold = DONE_HOLD_MS / 1000
        self._accent, self._colors = None, {}
        self._last_tick, self._last_push = time.perf_counter(), 0.0
        self._timer = QTimer(self, interval=16, timeout=self._tick)
        self._return_to_idle = QTimer(self, singleShot=True, timeout=lambda: self.set_mode("idle"))
        self._fresh_window = False              # a display changed: use a new native window next time
        self._display_timer = QTimer(self, singleShot=True, interval=1000, timeout=self._after_display_change)

    # ------------------------------------------------------------------ public API

    def start(self) -> None:
        """Go live: from now on the pill shows itself whenever it has something to show."""
        self.live = True
        self._style_window()
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._display_changed)
        app.primaryScreenChanged.connect(self._display_changed)
        for screen in app.screens():
            self._watch(screen)

    def set_mode(self, mode: str, message: str = "", hold_ms: int = 0, kind: str = "warning") -> None:
        if kind not in MESSAGE_KINDS:
            raise ValueError(f"unknown message kind {kind!r}; use one of {MESSAGE_KINDS}")
        self._return_to_idle.stop()
        if mode == "idle" and not self.show_idle:
            mode = "hidden"
        if mode != self.mode or message != self.message:
            # bars -> dots -> caret is one continuous motion; every other change is a crossfade
            if self.reduced or self.mode not in ("listening", "processing") or mode not in ("processing", "done"):
                self._crossfade()
            if mode != self.mode:
                self._t = 0.0
            if mode == "listening":
                self._history = [0.0] * BARS  # a fresh recording starts with a quiet waveform
        self.mode, self.message = mode, message
        if mode in ("message", "loading"):
            metrics = QFontMetricsF(self._font)
            self._text = metrics.elidedText(message, Qt.ElideRight, MAX_W - GLYPH - GAP - 2 * PAD)
            self._text_w = metrics.horizontalAdvance(self._text)
            self._notice = mode == "message" and kind == "notice"
            self._target = (self._text_w + GLYPH + GAP + 2 * PAD, PILL_H, 1.0)
        else:
            w, h, a = SHAPES[mode]
            self._target = (LOCKED_W if mode == "listening" and self.locked else w, h, a)
        if mode == "done":
            hold_ms = hold_ms or DONE_HOLD_MS
            self._hold = hold_ms / 1000
        if self.live and mode != "hidden":
            self._appear()  # on the monitor the mouse is on
        if hold_ms:
            self._return_to_idle.start(hold_ms)
        if self.reduced:
            self.w, self.h = self._target[0], self._target[1]  # no morphing, only fades
        if not self._timer.isActive():
            self._last_tick = time.perf_counter()
            self._timer.start()

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        if self.mode == "listening":
            self.set_mode("listening")

    # ------------------------------------------------------------------ the window

    def _appear(self) -> None:
        """Show the pill at the bottom centre of the screen the mouse is on, then check with
        Windows that it really is there, at the right size. If not, rebuild the window once."""
        if self._fresh_window:
            self._recreate_window()
        self._place()
        if not self.isVisible():
            self.show()
        problem = self._placement_problem()
        if problem:
            log.warning("pill window was %s (Qt scale %.2f; screens: %s); rebuilding it",
                        problem, self.devicePixelRatioF(), describe_screens())
            self._recreate_window()
            self._place()
            self.show()
            problem = self._placement_problem()
            log.log(logging.WARNING if problem else logging.INFO, "rebuilt the pill window: %s",
                    problem or "centred now")

    def _place(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        handle = self.windowHandle()
        if handle is not None and handle.screen() != screen:
            handle.setScreen(screen)
        area = screen.availableGeometry()
        self.move(area.x() + (area.width() - CANVAS_W) // 2, area.y() + area.height() - BOTTOM_OFFSET - CANVAS_H // 2)

    def _placement_problem(self) -> str:
        hwnd = int(self.winId())
        r, info = wintypes.RECT(), _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
        _user32.GetWindowRect(hwnd, ctypes.byref(r))
        _user32.GetMonitorInfoW(_user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), ctypes.byref(info))
        w = info.rcWork
        return placement_problem((r.left, r.top, r.right, r.bottom), (w.left, w.top, w.right, w.bottom),
                                 _user32.GetDpiForWindow(hwnd))

    def _recreate_window(self) -> None:
        """Throw the native window away. The new one starts with the display's real scale."""
        self._fresh_window = False
        self.hide()
        self.destroy()
        self._style_window()  # creates the new window (still hidden)

    def _style_window(self) -> None:
        hwnd = int(self.winId())
        ex = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        # NOACTIVATE: never steal focus. TRANSPARENT: click-through. TOOLWINDOW: no taskbar button.
        _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)

    def _watch(self, screen) -> None:
        for signal in (screen.geometryChanged, screen.availableGeometryChanged, screen.logicalDotsPerInchChanged):
            signal.connect(self._display_changed)

    def _on_screen_added(self, screen) -> None:
        self._watch(screen)
        self._display_changed()

    def _display_changed(self, *_args) -> None:
        self._display_timer.start()  # changes come in bursts (sleep, docking): act once, a moment later

    def _after_display_change(self) -> None:
        log.info("displays changed: %s", describe_screens())
        self._fresh_window = True  # the next appearance gets a new native window
        if self.isVisible() and self.mode != "hidden":
            self._appear()  # showing something: move it to a fresh window now
        # hidden, even while it fades out: nothing to show, so no window is made or shown

    # ------------------------------------------------------------------ animation

    def _crossfade(self) -> None:
        """What's in the capsule now fades out while the new content fades in."""
        if self.bg_a > 0.01 and self.content_a > 0.05 and self.mode not in ("hidden", "idle"):
            self._old, self._old_a = self._content(frozen=True), self.content_a
        self.content_a = 0.0

    def _content(self, frozen: bool = False) -> dict:
        """Everything needed to draw what's inside the capsule. Frozen: a copy that stops moving."""
        bars, bar_a = (list(self._bars), list(self._bar_a)) if frozen else (self._bars, self._bar_a)
        return {"mode": self.mode, "text": self._text, "text_w": self._text_w, "notice": self._notice,
                "bars": bars, "bar_a": bar_a, "t": self._t, "spin": self._phase,
                "lock_x": self._lock_x, "lock_a": self._lock_a}

    def _tick(self) -> None:
        now = time.perf_counter()
        dt, self._last_tick = min(now - self._last_tick, 0.1), now
        self._t += dt
        self._phase += dt
        tw, th, ta = self._target
        lock = float(self.locked and self.mode == "listening")
        if self.reduced:  # sizes snap; everything else is a 120 ms fade
            self.w, self.h, self._lock_x = tw, th, lock
            self.bg_a = _ramp(self.bg_a, ta, dt, FADE_S)
            self.content_a = _ramp(self.content_a, 1.0, dt, FADE_S)
            self._old_a = _ramp(self._old_a, 0.0, dt, FADE_S)
            self._lock_a = _ramp(self._lock_a, lock, dt, FADE_S)
        else:
            self.w = _smooth(self.w, tw, dt, 0.07)
            self.h = _smooth(self.h, th, dt, 0.07)
            self.bg_a = _smooth(self.bg_a, ta, dt, 0.09)
            self.content_a = _smooth(self.content_a, 1.0, dt, 0.09)
            self._old_a = _smooth(self._old_a, 0.0, dt, 0.06)
            self._lock_x = _smooth(self._lock_x, lock, dt, 0.07)
            self._lock_a = _smooth(self._lock_a, lock, dt, 0.09)
        if self.mode == "done":
            self.bg_a = min(self.bg_a, self._done_fade())

        raw = level_to_unit(self.level_source()) if (self.mode == "listening" and self.level_source) else 0.0
        self._level = _smooth(self._level, raw, dt, 0.03 if raw > self._level else 0.16)  # fast attack, slow release
        if self.mode == "listening" and now - self._last_push > 0.04:
            # scroll the history outwards from the centre, so speech "radiates" both ways
            half = self._history[:CENTER][1:] + [self._level]
            self._history = half + [self._level] + half[::-1]
            self._last_push = now

        for i in range(BARS):
            goal = self._history[i] * _envelope(i) if self.mode == "listening" else 0.0
            if (self.reduced and self.mode != "listening") or self.mode == "starting":
                self._bars[i] = goal  # the dots appear at once, under the crossfade
            else:
                self._bars[i] = _smooth(self._bars[i], goal, dt, 0.045)
            if self.mode in ("listening", "starting"):
                self._bar_a[i] = 1.0
            elif self.mode == "processing":
                self._bar_a[i] = self._wave(i)
            # done: the dots keep their last opacity while they gather into the caret

        self.update()
        still = self.mode in ("hidden", "idle", "message", "starting") or (self.reduced and self.mode in ("processing", "loading"))
        settled = abs(self.bg_a - ta) < 0.01 and (self.mode == "hidden" or (
            abs(self.w - tw) < 0.3 and abs(self.h - th) < 0.3 and self.content_a > 0.99 and self._old_a < 0.01))
        if still and settled:
            self.w, self.h, self.bg_a, self.content_a, self._old, self._old_a = tw, th, ta, 1.0, None, 0.0
            self._lock_x = self._lock_a = 0.0
            self._timer.stop()  # nothing moving: stop repainting (idle CPU ~0)
            if self.mode == "hidden" and self.live:
                self.hide()     # faded out: no window at all until the next dictation

    def _wave(self, i: int) -> float:
        """Processing: a dot's opacity. Once the bars are dots, a gentle wave runs from the centre
        out: 700 ms period, 60 % to 100 %. Reduced motion: the dots hold at 60 %."""
        if self.reduced:
            return DOT_FLOOR
        depth = _ease_out((self._t - 0.15) / 0.3)  # grows in after the bars have become dots
        u = self._t / WAVE_S - abs(i - CENTER) / WAVE_DOTS
        return 1 - (1 - DOT_FLOOR) * depth * (0.5 - 0.5 * math.cos(2 * math.pi * u))

    def _done_fade(self) -> float:
        """Done ends with the whole pill fading out over the last 160 ms (InCubic); then no window.
        Reduced motion: the finished logo shows for 400 ms, then fades over 120 ms."""
        if self.reduced:
            return 1 - _clamp((self._t - FADE_S - 0.4) / FADE_S)
        return 1 - _ease_in((self._t - self._hold + 0.16) / 0.16)

    # ------------------------------------------------------------------ painting

    def _palette(self) -> dict:
        """The dark tokens in the chosen accent. The pill is always dark, in light mode too: it
        floats over any app like a hardware object, and a dark capsule reads over everything."""
        accent = brand.current()["accentName"]
        if accent != self._accent:
            tokens = brand.tokens("dark", accent)
            self._colors = {k: QColor(tokens[k]) for k in ("pillBg", "pillStroke", "accentText", "textPrimary",
                                                            "warning")}
            self._accent = accent
        return self._colors

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        self._paint(p, self.devicePixelRatioF())
        p.end()

    def _paint(self, p: QPainter, dpr: float) -> None:
        """Draws the pill. dpr (device pixels per logical px) puts edges on whole device pixels."""
        a = self.bg_a
        if a < 0.005:
            return
        colors = self._palette()
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = CANVAS_W / 2, CANVAS_H / 2
        left, top = _snap(cx - self.w / 2, dpr), _snap(cy - self.h / 2, dpr)
        rect = QRectF(left, top, _snap(cx + self.w / 2, dpr) - left, _snap(cy + self.h / 2, dpr) - top)
        radius = rect.height() / 2
        self._paint_shadow(p, rect, a, dpr)
        p.setPen(Qt.NoPen)
        p.setBrush(_alpha(colors["pillBg"], a))
        p.drawRoundedRect(rect, radius, radius)
        hair = 1 / dpr  # the hairline: one device pixel, just inside the edge
        p.setPen(QPen(_alpha(colors["pillStroke"], a), hair))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(hair / 2, hair / 2, -hair / 2, -hair / 2), radius - hair / 2, radius - hair / 2)

        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.setClipPath(clip)
        if self._old is not None and self._old_a > 0.005:
            self._paint_content(p, rect, self._old, self._old_a * a, colors, dpr)
        self._paint_content(p, rect, self._content(), self.content_a * a, colors, dpr)

    def _paint_shadow(self, p: QPainter, rect: QRectF, a: float, dpr: float) -> None:
        """The neutral shadow (y 4, blur 16, black 30 %): a blurred capsule, drawn as a straight
        middle (a vertical gradient) and two round ends (radial gradients), so any size costs the same."""
        sigma, r = SHADOW_BLUR / 2, rect.height() / 2
        reach = r + 3 * sigma
        cy = rect.center().y() + SHADOW_Y
        profile = []
        for k in range(17):
            ink = QColor(0, 0, 0)
            ink.setAlphaF(SHADOW_A * a * _blurred(k / 16 * reach, r, sigma))
            profile.append((k / 16, ink))
        middle = QLinearGradient(0, cy - reach, 0, cy + reach)
        for pos, ink in profile:
            middle.setColorAt(0.5 - pos / 2, ink)
            middle.setColorAt(0.5 + pos / 2, ink)
        # the three pieces meet on whole device pixels, so their edges don't overlap into a seam
        mid_l = _snap(rect.left() + r, dpr)
        mid_r = max(mid_l, _snap(rect.right() - r, dpr))
        p.fillRect(QRectF(mid_l, cy - reach, mid_r - mid_l, 2 * reach), middle)
        for x, piece in ((rect.left() + r, QRectF(mid_l - reach - 1, cy - reach, reach + 1, 2 * reach)),
                         (rect.right() - r, QRectF(mid_r, cy - reach, reach + 1, 2 * reach))):
            end = QRadialGradient(QPointF(x, cy), reach)
            for pos, ink in profile:
                end.setColorAt(pos, ink)
            p.fillRect(piece, end)

    def _paint_content(self, p: QPainter, rect: QRectF, c: dict, alpha: float, colors: dict, dpr: float) -> None:
        if alpha < 0.005:
            return
        p.setPen(Qt.NoPen)
        voice = colors["accentText"]
        if c["mode"] in ("listening", "processing"):
            self._paint_bars(p, rect, c, alpha, voice, colors, dpr)
        elif c["mode"] == "starting":  # resting dots, not yet the voice's colour
            self._paint_bars(p, rect, c, alpha * STARTING_A, colors["textPrimary"], colors, dpr)
        elif c["mode"] == "done":
            self._paint_done(p, c, alpha, voice, colors, dpr)
        elif c["mode"] in ("message", "loading"):
            self._paint_message(p, c, alpha, colors, dpr)

    def _paint_bars(self, p: QPainter, rect: QRectF, c: dict, alpha: float, voice: QColor, colors: dict,
                    dpr: float) -> None:
        """Listening: your voice as solid bars. Processing: the same bars, settled into dots.
        Starting: the dots at rest, in the ink it's given (dim white)."""
        cx = CANVAS_W / 2 - c["lock_x"] * (LOCKED_W - LISTEN_W) / 2  # hands-free: move over for the stop mark
        cy = CANVAS_H / 2
        for i in range(BARS):
            h = BAR_MIN + (BAR_MAX - BAR_MIN) * c["bars"][i]
            _bar(p, cx + (i - CENTER) * (BAR_W + BAR_GAP), cy, h, voice, alpha * c["bar_a"][i], dpr)
        if c["lock_a"] > 0.01:  # hands-free: a stop mark, "tap to finish", centred in the round end
            p.setBrush(_alpha(colors["textPrimary"], 0.8 * alpha * c["lock_a"]))
            p.drawRoundedRect(QRectF(_snap(rect.right() - 22, dpr), _snap(cy - 4, dpr), 8, 8), 2, 2)

    def _paint_done(self, p: QPainter, c: dict, alpha: float, voice: QColor, colors: dict, dpr: float) -> None:
        """The caret signature: the dots gather into a white caret, then the logo's three bars step out
        to its left, and for a beat the pill is the logo."""
        t, cy = c["t"], CANVAS_H / 2
        stroke = max(1, math.ceil(CARET_W * dpr - 0.5)) / dpr  # whole device pixels, halves rounded down
        cx = _snap(CANVAS_W / 2 + CARET_DX - stroke / 2, dpr) + stroke / 2  # the caret's stem on device pixels
        if self.reduced:  # the finished logo, no motion: it crossfades in
            gather, caret, steps = 1.0, 1.0, (1.0, 1.0, 1.0)
        else:
            gather = _ease_out(t / 0.16)                                   # 0-160 ms
            caret = _ease_out((t - 0.10) / 0.10)                           # 100-200 ms
            steps = [_emphasized((t - 0.16 - 0.04 * k) / 0.14) for k in range(len(LOGO))]  # from 160 ms, 40 ms apart
        if gather < 1:
            for i in range(BARS):
                x = CANVAS_W / 2 + (i - CENTER) * (BAR_W + BAR_GAP)
                h = BAR_MIN + (BAR_MAX - BAR_MIN) * c["bars"][i]
                _bar(p, x + (cx - x) * gather, cy, h + (BAR_MIN - h) * gather, voice,
                     alpha * c["bar_a"][i] * (1 - gather), dpr)
        for k, (height, opacity) in enumerate(LOGO):  # each steps out from behind the one before it
            if steps[k] > 0:
                x = cx - LOGO_GAP - LOGO_STEP * (k - 1 + steps[k])
                _bar(p, x, cy, height, voice, alpha * opacity * steps[k], dpr)
        if caret > 0:
            brand.paint_caret(p, cx, cy, CARET_H, stroke, _alpha(colors["textPrimary"], alpha * caret))

    def _paint_message(self, p: QPainter, c: dict, alpha: float, colors: dict, dpr: float) -> None:
        """A 16 px glyph (or the spinner) and the text, centred together, so they hold still while
        the capsule resizes around them."""
        left = _snap(CANVAS_W / 2 - (GLYPH + GAP + c["text_w"]) / 2, dpr)
        top = _snap(CANVAS_H / 2 - GLYPH / 2, dpr)
        quiet = _alpha(colors["textPrimary"], 0.7 * alpha)
        if c["mode"] == "loading":  # a 2 px ring, one turn a second (still under reduced motion)
            p.setPen(QPen(quiet, 2, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            start = 90 if self.reduced else 90 - (c["spin"] % 1.0) * 360
            p.drawArc(QRectF(left + 1, top + 1, GLYPH - 2, GLYPH - 2), int(start * 16), -100 * 16)
        else:
            p.setFont(self._icons)
            p.setPen(quiet if c["notice"] else _alpha(colors["warning"], alpha))
            p.drawText(QPointF(left, top + GLYPH), INFO_GLYPH if c["notice"] else WARNING_GLYPH)
        p.setFont(self._font)
        p.setPen(_alpha(colors["textPrimary"], alpha))
        baseline = _snap(CANVAS_H / 2 + QFontMetricsF(self._font).capHeight() / 2, dpr)
        p.drawText(QPointF(left + GLYPH + GAP, baseline), c["text"])
