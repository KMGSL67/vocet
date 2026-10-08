"""The first-run welcome's logic (ui/Welcome.qml shows it).

- Who sees it: brand-new users only. settings.load() marks an existing settings.json from
  before the welcome as welcomed; `migrate()` does the same when there's history (a user whose
  settings file went missing). Test instances (VOCET_TEST_WAV) never see it unless a test sets
  VOCET_WELCOME=1, so an end-to-end test can never have it steal the focus.
- It's shown once: finishing, skipping (Esc) or closing the window all count as seen.
  Settings › General › Welcome shows it again.
- The microphone test (`MicTest`): the mic is opened only when you press "Test microphone",
  and closed after `DURATION_MS` or when you press it again, whatever happens first.
"""

import logging
import os
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from . import settings as settings_mod

log = logging.getLogger(__name__)

DURATION_MS = 5000        # the mic test stops by itself after this long
LEVEL_INTERVAL_MS = 33    # the meter's refresh while testing (like the window logo's)


def migrate(settings: dict, has_history: bool) -> bool:
    """Marks someone who has used Vocet before as welcomed. True if the settings changed."""
    if settings.get("welcomed_version", 0) >= settings_mod.WELCOME_VERSION or not has_history:
        return False
    settings["welcomed_version"] = settings_mod.WELCOME_VERSION
    return True


def should_show(settings: dict, test_mode: bool, env: dict | None = None) -> bool:
    """Whether this start shows the welcome."""
    env = os.environ if env is None else env
    if test_mode and env.get("VOCET_WELCOME") != "1":
        return False
    return settings.get("welcomed_version", 0) < settings_mod.WELCOME_VERSION


def mark_seen(settings: dict) -> bool:
    """True if this changed the settings (they then need saving)."""
    if settings.get("welcomed_version", 0) >= settings_mod.WELCOME_VERSION:
        return False
    settings["welcomed_version"] = settings_mod.WELCOME_VERSION
    return True


class MicTest(QObject):
    """"Test microphone": opens the chosen mic, reports its level, closes it again.

    `opener()` returns a started-or-startable recorder with .start(), .level (RMS 0..1), .stop()
    and .close() (audio.Recorder, or a fake in tests). Nothing runs while no test is running:
    no timers, no open device."""

    runningChanged = Signal(bool)
    levelChanged = Signal(float)     # 0..1, on the same dB scale as the pill (pill.level_to_unit)
    failed = Signal(str)

    def __init__(self, opener: Callable[[], object] | None = None, duration_ms: int = DURATION_MS):
        super().__init__()
        self.opener = opener
        self.recorder = None
        self.level = 0.0
        self._stop_timer = QTimer(self, singleShot=True, interval=duration_ms, timeout=self.stop)
        self._level_timer = QTimer(self, interval=LEVEL_INTERVAL_MS, timeout=self._poll)

    @property
    def running(self) -> bool:
        return self.recorder is not None

    def start(self) -> bool:
        if self.running or self.opener is None:
            return False
        try:
            rec = self.opener()
            rec.start()
        except Exception:  # noqa: BLE001 - a missing or busy mic is one sentence, not a crash
            log.exception("microphone test: couldn't open the microphone")
            self.failed.emit("Couldn’t open the microphone. Check it’s plugged in and that Windows lets apps use it.")
            return False
        self.recorder = rec
        self._stop_timer.start()
        self._level_timer.start()
        log.info("microphone test started")
        self.runningChanged.emit(True)
        return True

    def stop(self) -> None:
        self._stop_timer.stop()
        self._level_timer.stop()
        rec, self.recorder = self.recorder, None
        if rec is None:
            return
        for step in (rec.stop, rec.close):
            try:
                step()
            except Exception:  # noqa: BLE001
                log.exception("microphone test: closing the microphone")
        self._set_level(0.0)
        log.info("microphone test stopped; microphone closed")
        self.runningChanged.emit(False)

    def toggle(self) -> None:
        if self.running:
            self.stop()
        else:
            self.start()

    def _poll(self) -> None:
        if self.recorder is not None:
            from .pill import level_to_unit
            self._set_level(level_to_unit(float(getattr(self.recorder, "level", 0.0))))

    def _set_level(self, level: float) -> None:
        if abs(level - self.level) > 0.002 or (level == 0.0 and self.level != 0.0):
            self.level = level
            self.levelChanged.emit(level)
