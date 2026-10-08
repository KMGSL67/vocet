"""The Vocet window (history, dictionary, snippets, settings), built with Qt Quick (QML).

Why QML for the window, when the pill uses QPainter? The window is mostly lists,
text fields and transitions, which QML describes declaratively ("this fades in
when active") and animates on the GPU. The pill is one custom-drawn shape that
has to be tiny and exact, so it's painted by hand. Files:

    window.py        this file: the bridge. Python owns data and logic
    ui/Main.qml      window layout, navigation
    ui/*.qml         pages and small reusable controls

QML reads Python through two context properties:
    theme    the flat token dict from brand.py (one source for pill and window), re-published
             when the accent, Windows' light/dark, Text size or a contrast theme changes
    backend  the Backend object below: data as properties, actions as slots
"""

import ctypes
import logging
import os
import re
import winreg
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from urllib.parse import unquote

from PySide6.QtCore import (QAbstractListModel, QAbstractNativeEventFilter, QCoreApplication, QFileInfo, QMetaObject,
                            QModelIndex, QObject, Property, QSize, QTimer, QUrl, Qt, Signal, Slot)
from PySide6.QtGui import QGuiApplication, QPalette, QPixmap, QWindow
from PySide6.QtQml import QJSValue, QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (imported so the root object is typed as a QQuickWindow)

from . import brand, settings as settings_mod, welcome
from .history import History, day_label

log = logging.getLogger(__name__)
UI_DIR = Path(__file__).resolve().parent / "ui"

# Follow Windows' light or dark mode. False keeps Vocet dark whatever Windows
# uses.
FOLLOW_WINDOWS_APPEARANCE = True
# Hide the caption's own icon and title, so the sidebar lockup is the only brand mark.
# v4: checked on screen; the caption is a plain black (or white) strip with the system
# buttons over the floating sidebar. The title still names the window in the taskbar, Alt+Tab
# and screen readers.
HIDE_CAPTION_TITLE = True

# ------------------------------------------------------------------ what Windows says about appearance

_user32 = ctypes.WinDLL("user32")
_user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
_user32.SystemParametersInfoW.restype = wintypes.BOOL
SPI_GETCLIENTAREAANIMATION = 0x1042
WM_SYSCOLORCHANGE, WM_SETTINGCHANGE = 0x0015, 0x001A


def windows_mode() -> str:
    """"dark" or "light", from Settings › Personalization › Colors (unknown: dark, the default)."""
    if not FOLLOW_WINDOWS_APPEARANCE:
        return "dark"
    return "light" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light else "dark"


def text_scale_factor() -> float:
    """Settings › Accessibility › Text size, 1.0-2.25. The value only exists once someone moves the slider."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Accessibility") as key:
            percent = int(winreg.QueryValueEx(key, "TextScaleFactor")[0])
    except (OSError, TypeError, ValueError):
        return 1.0
    return min(225, max(100, percent)) / 100


def reduced_motion() -> bool:
    """Settings › Accessibility › Visual effects › Animation effects is off."""
    enabled = wintypes.BOOL(True)  # a 4-byte BOOL: SPI writes that much
    _user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0)
    return not enabled.value


def high_contrast() -> bool:
    """A Windows contrast theme is on (Qt 6.10+ reports it; older Qt: never)."""
    hints = QGuiApplication.styleHints()
    if not hasattr(hints, "accessibility"):
        return False
    return hints.accessibility().contrastPreference() == Qt.ContrastPreference.HighContrast


def always_show_scrollbars() -> bool:
    """Settings › Accessibility › Visual effects › "Automatically hide scroll bars in Windows"
    is off (HKCU\\Control Panel\\Accessibility\\DynamicScrollbars, 0 = always show)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Accessibility") as key:
            value = int(winreg.QueryValueEx(key, "DynamicScrollbars")[0])
    except (OSError, TypeError, ValueError):
        return False  # key missing: Windows' own default is to auto-hide
    return value == 0


def system_palette() -> dict:
    """The colours of the current contrast theme, from Qt's system palette (for brand.tokens)."""
    pal = QGuiApplication.palette()
    role = lambda r, group=QPalette.Active: pal.color(group, r).name().upper()
    return {"window": role(QPalette.Window), "windowText": role(QPalette.WindowText), "base": role(QPalette.Base),
            "highlight": role(QPalette.Highlight), "highlightedText": role(QPalette.HighlightedText),
            "link": role(QPalette.Link), "grayText": role(QPalette.WindowText, QPalette.Disabled)}


class _SettingChangeFilter(QAbstractNativeEventFilter):
    """Calls on_change for WM_SETTINGCHANGE and WM_SYSCOLORCHANGE. Qt runs it for every native
    message, so it only reads the message id (on Windows, `message` is always an MSG*)."""

    def __init__(self, on_change):
        super().__init__()
        self._on_change = on_change

    def nativeEventFilter(self, event_type, message):
        # int() first: `message` is a shiboken VoidPtr, which is falsy even when it isn't null.
        address = int(message) if message is not None else 0
        if address and wintypes.MSG.from_address(address).message in (WM_SETTINGCHANGE, WM_SYSCOLORCHANGE):
            self._on_change()
        return False, 0


class SystemAppearance(QObject):
    """Windows' light/dark, Text size, Animation effects and contrast theme, kept live.

    Windows announces a change with a burst of WM_SETTINGCHANGE messages, so they're debounced
    and `changed` fires once per real change. Nothing polls: an idle Vocet stays at 0 % CPU.
    """

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.mode, self.text_scale, self.reduced_motion, self.high_contrast, self.palette = self._read()
        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self._reread)
        hints = QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(lambda *_: self._debounce.start())
        if hasattr(hints, "accessibility"):
            hints.accessibility().contrastPreferenceChanged.connect(lambda *_: self._debounce.start())
        self._filter = _SettingChangeFilter(self._debounce.start)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        # Windows sends setting changes to top-level windows only. This hidden one hears them
        # even while no Vocet window exists yet.
        self._ear = QWindow()
        self._ear.setFlags(Qt.Tool)
        self._ear.create()

    @staticmethod
    def _read() -> tuple:
        contrast = high_contrast()
        return windows_mode(), text_scale_factor(), reduced_motion(), contrast, system_palette() if contrast else None

    def _reread(self) -> None:
        now = self._read()
        if now != (self.mode, self.text_scale, self.reduced_motion, self.high_contrast, self.palette):
            self.mode, self.text_scale, self.reduced_motion, self.high_contrast, self.palette = now
            log.info("appearance: %s, text %.0f %%, reduced motion %s, contrast theme %s", self.mode,
                     self.text_scale * 100, self.reduced_motion, self.high_contrast)
            self.changed.emit()


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_kernel32.DeviceIoControl.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_INVALID_HANDLE = wintypes.HANDLE(-1).value
IO_REPARSE_TAG_APPEXECLINK = 0x8000001B


def app_exec_link_target(path: str) -> str:
    """The real program behind a Store app's alias in %LOCALAPPDATA%/Microsoft/WindowsApps (an
    "app execution alias" reparse point, which os.readlink can't follow), or "" if it isn't one."""
    handle = _kernel32.CreateFileW(path, 0x80, 7, None, 3, 0x00200000 | 0x02000000, None)  # FILE_READ_ATTRIBUTES,
    if handle in (None, _INVALID_HANDLE):  # share all, OPEN_EXISTING, OPEN_REPARSE_POINT | BACKUP_SEMANTICS
        return ""
    try:
        buf = ctypes.create_string_buffer(16384)
        got = wintypes.DWORD()
        if not _kernel32.DeviceIoControl(handle, 0x000900A8, None, 0, buf, len(buf), ctypes.byref(got), None):
            return ""  # FSCTL_GET_REPARSE_POINT
        data = buf.raw[:got.value]
        if len(data) < 12 or int.from_bytes(data[:4], "little") != IO_REPARSE_TAG_APPEXECLINK:
            return ""
        parts = data[12:].decode("utf-16-le", "ignore").split("\0")  # package id, app id, target, type
        return parts[2] if len(parts) > 2 else ""
    finally:
        _kernel32.CloseHandle(handle)


def _version_key(name: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", name))


def resolve_program(path: str) -> str:
    """The program whose icon stands for `path`. Store aliases resolve to the packaged exe, and a
    Squirrel launcher (Discord, Slack: <app>/Update.exe) to the newest app-*/<App>.exe beside it."""
    p = Path(path)
    if p.parent.name.lower() == "windowsapps" and p.parent.parent.name.lower() == "microsoft":
        return app_exec_link_target(path) or path
    if p.name.lower() == "update.exe":
        builds = sorted((d for d in p.parent.glob("app-*") if d.is_dir()), key=lambda d: _version_key(d.name),
                        reverse=True)
        for build in builds:
            exe = build / (p.parent.name + ".exe")
            if exe.exists():
                return str(exe)
    return path


def package_logo(program: str) -> str:
    """The Start-menu logo of the Store package `program` lives in (Square44x44Logo in its
    AppxManifest.xml), preferring the unplated 64/48/32 px asset; "" if there isn't one."""
    root = Path(program).parent
    while root.parent != root and root.parent.name.lower() != "windowsapps":
        root = root.parent
    manifest = root / "AppxManifest.xml"
    try:
        match = re.search(r'Square44x44Logo="([^"]+)"', manifest.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return ""
    if not match:
        return ""
    logo = root / match.group(1)
    for qualifier in ("targetsize-64_altform-unplated", "targetsize-48_altform-unplated",
                      "targetsize-32_altform-unplated", "targetsize-64", "scale-200", "scale-100"):
        candidate = logo.with_name(f"{logo.stem}.{qualifier}{logo.suffix}")
        if candidate.exists():
            return str(candidate)
    return str(logo) if logo.exists() else ""


class AppIconProvider(QQuickImageProvider):
    """Serves "image://appicon/<program path>": the real icon of the app a dictation went into.
    Store aliases and Squirrel launchers are resolved to the real program first. When Windows only
    has its generic program icon, it serves a 1 px transparent image, so C.AppIcon shows its own
    app glyph instead."""

    def __init__(self):
        super().__init__(QQuickImageProvider.Pixmap)
        self._icons = QFileIconProvider()
        self._cache: dict[str, QPixmap] = {}
        self._generic = None  # Windows' "program without an icon" image, made on first use

    def _pixmap(self, path: str) -> QPixmap:
        icon = self._icons.icon(QFileInfo(path))
        return icon.pixmap(64, 64) if not icon.isNull() else QPixmap()

    def _is_generic(self, pix: QPixmap) -> bool:
        if self._generic is None:  # a program that doesn't exist gets exactly the generic icon
            self._generic = self._pixmap(str(Path(os.environ.get("TEMP", "C:\\")) / "vocet-no-such-program.exe"))
        return pix.isNull() or (not self._generic.isNull() and pix.toImage() == self._generic.toImage())

    def _load(self, path: str) -> QPixmap:
        if not path or not Path(path).exists():
            return QPixmap()
        program = resolve_program(path)
        pix = self._pixmap(program)
        if not self._is_generic(pix):
            return pix
        in_package = any(part.lower() == "windowsapps" for part in Path(program).parts)
        logo = package_logo(program) if in_package else ""
        return QPixmap(logo) if logo else QPixmap()

    def requestPixmap(self, id_: str, size: QSize, requested: QSize) -> QPixmap:
        path = unquote(id_)
        if path not in self._cache:
            try:
                self._cache[path] = self._load(path)
            except Exception:  # an icon is never worth an error: QML falls back to its glyph
                log.exception("app icon for %s", path)
                self._cache[path] = QPixmap()
        pix = self._cache[path]
        if pix.isNull():  # "no icon" is a 1 px transparent image: a null one makes Qt log a warning
            pix = QPixmap(1, 1)
            pix.fill(Qt.transparent)
        if size is not None:
            size.setWidth(pix.width())
            size.setHeight(pix.height())
        return pix


def full_time(ts: float) -> str:
    d = datetime.fromtimestamp(ts)
    return f"{d:%A} {d.day} {d:%B %Y} at {d:%H:%M}"


class HistoryModel(QAbstractListModel):
    ROLES = {Qt.UserRole + i: name for i, name in enumerate(
        (b"entryId", b"text", b"time", b"createdAt", b"fullTime", b"day", b"app", b"appPath", b"language", b"words",
         b"outcome"))}

    def __init__(self, history: History):
        super().__init__()
        self.history = history
        self.rows: list[dict] = []
        self.query = ""

    def roleNames(self):
        return self.ROLES

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        name = self.ROLES.get(role, b"").decode()
        if name == "entryId":
            return row["id"]
        if name == "time":
            return datetime.fromtimestamp(row["created_at"]).strftime("%H:%M")
        if name == "createdAt":  # Home turns it into "Just now" / "5 min ago" for the last hour
            return float(row["created_at"])
        if name == "fullTime":  # the tooltip on the time: "Sunday 28 September 2026 at 20:24"
            return full_time(row["created_at"])
        if name == "day":
            return day_label(row["created_at"])
        if name == "appPath":
            return row.get("app_path") or ""
        if name == "language":
            return row.get("language") or ""
        return row.get(name)

    def reload(self, query: str | None = None) -> None:
        if query is not None:
            self.query = query
        self.beginResetModel()
        self.rows = self.history.recent(query=self.query)
        self.endResetModel()

    def prepend(self, row: dict) -> None:
        if self.query and self.query.lower() not in row["text"].lower():
            return
        self.beginInsertRows(QModelIndex(), 0, 0)  # an insert (not a reset) lets the list animate it in
        self.rows.insert(0, row)
        self.endInsertRows()

    def remove(self, entry_id: int) -> dict | None:
        for i, row in enumerate(self.rows):
            if row["id"] == entry_id:
                self.beginRemoveRows(QModelIndex(), i, i)
                del self.rows[i]
                self.endRemoveRows()
                return row
        return None


class Backend(QObject):
    settingsChanged = Signal()
    statsChanged = Signal()
    listeningChanged = Signal()
    micLevelChanged = Signal()
    statusChanged = Signal()
    loadingChanged = Signal()          # loading and loadProgress change together
    toast = Signal(str, bool)          # message, offer undo
    settingEdited = Signal(str)        # -> app.py reacts (hotkey, model, startup...)
    appearanceChanged = Signal()       # tokens re-published, or Animation effects changed
    resumeRequested = Signal()         # -> app.py: resume from pause (see resume())
    aiFormattingChanged = Signal()     # AI formatting's state (ai_format.py) changed
    welcomeChanged = Signal()          # the first-run welcome opened or closed
    micTestChanged = Signal()          # "Test microphone" started or stopped
    micTestLevelChanged = Signal()
    micTestFailed = Signal(str)
    speechModelChanged = Signal()      # the speech model's download state (model_download.py)
    downloadRequested = Signal()       # -> app.py: start the speech-model download
    downloadCancelRequested = Signal() # -> app.py: cancel it
    dictated = Signal(bool)            # a dictation was pasted; True if it went into Vocet's own window

    def __init__(self, settings: dict, history: History):
        super().__init__()
        self._settings = settings
        self.history = history
        self.model = HistoryModel(history)
        self.model.reload()
        self._stats = history.stats()
        self._mic_level = 0.0
        self._listening = False
        self._status = "Loading the speech model"
        self._blocked = 0
        self._deleted: dict | None = None
        self._mics: list[dict] = []
        self._reduced_motion = reduced_motion()
        self._always_show_scrollbars = always_show_scrollbars()
        self._loading = True     # the speech model starts loading as soon as the app starts
        self._load_progress = 0.0
        self._ai_state, self._ai_message = "off", ""
        self._welcome_open = False
        self._speech_model = {"state": "ready"}
        self.mic_test = welcome.MicTest()  # app.py sets its opener (the chosen mic, or the test WAV)
        self.mic_test.runningChanged.connect(lambda _running: self.micTestChanged.emit())
        self.mic_test.levelChanged.connect(lambda _level: self.micTestLevelChanged.emit())
        self.mic_test.failed.connect(self.micTestFailed)

    # ------------------------------------------------------------------ properties for QML

    @Property("QVariantMap", notify=settingsChanged)
    def settings(self):
        return self._settings

    @Property("QVariantMap", notify=statsChanged)
    def stats(self):
        return self._stats

    @Property(QObject, constant=True)
    def historyModel(self):
        return self.model

    @Property(float, notify=micLevelChanged)
    def micLevel(self):
        return self._mic_level

    @Property(bool, notify=listeningChanged)
    def listening(self):
        return self._listening

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(int, notify=statusChanged)
    def networkBlocked(self):
        return self._blocked

    @Property(bool, notify=appearanceChanged)
    def reducedMotion(self):
        return self._reduced_motion

    @Property(bool, constant=True)
    def alwaysShowScrollbars(self):
        return self._always_show_scrollbars

    @Property(bool, notify=loadingChanged)
    def loading(self):
        return self._loading

    @Property(str, notify=aiFormattingChanged)
    def aiFormattingStatus(self):
        """One sentence for Settings under the AI formatting switch: "Getting AI formatting ready…",
        "On", or why it can't run here. "" = off (the switch's own description shows)."""
        return self._ai_message

    @Property(bool, notify=aiFormattingChanged)
    def aiFormattingAvailable(self):
        """False: this PC can't run it (not downloaded, memory, graphics chip, too slow)."""
        return self._ai_state != "unavailable"

    @Property(float, notify=loadingChanged)
    def loadProgress(self):
        return self._load_progress

    @Property(bool, notify=welcomeChanged)
    def welcomeOpen(self):
        """The first-run welcome is showing (ui/Welcome.qml)."""
        return self._welcome_open

    @Property(bool, notify=micTestChanged)
    def micTesting(self):
        return self.mic_test.running

    @Property(float, notify=micTestLevelChanged)
    def micTestLevel(self):
        return self.mic_test.level

    @Property("QVariantMap", notify=speechModelChanged)
    def speechModel(self):
        """{state: ready | needed | downloading | verifying | failed | cancelled, done, total,
        progress 0-1, size "0.8 GB", doneLabel, source "Hugging Face", message}."""
        return self._speech_model

    @Property("QVariantList", notify=appearanceChanged)
    def accents(self):
        """Settings › Appearance swatches: name, label, and the fill for the current light/dark."""
        mode = brand.current()["mode"]
        return [{"name": k, "label": a["label"], "fill": a[mode]["accent"]} for k, a in brand.ACCENTS.items()]

    @Property("QVariantList", constant=True)
    def hotkeys(self):
        return [{"key": k, "label": label} for k, (_vk, label) in settings_mod.HOTKEYS.items()]

    @Property("QVariantList", constant=True)
    def themes(self):
        return [{"key": k, "label": t["label"], "colors": list(t["spectrum"])} for k, t in brand.THEMES.items()]

    @Property("QVariantList", constant=True)
    def presets(self):
        return [{"key": k, "label": v["label"], "detail": v["detail"], "multilingual": v["multilingual"]}
                for k, v in settings_mod.MODEL_PRESETS.items()]

    @Property("QVariantList", constant=True)
    def languages(self):
        return [{"key": k, "label": label} for k, label in settings_mod.LANGUAGES]

    @Property("QVariantList", constant=True)
    def spokenLanguages(self):
        """Settings › Languages you speak: each language in its own name, a detail and a badge."""
        return [{"key": k, "label": label, "detail": "" if note == "Beta" else note, "badge": note if note == "Beta" else ""}
                for k, label, note in settings_mod.SPOKEN_LANGUAGES]

    @Property(str, notify=settingsChanged)
    def aiFormattingLanguageNote(self):
        """One sentence when AI formatting skips some of your languages (it only runs where it passed
        the checker: ai_format.LANGUAGES), else ""."""
        from .ai_format import LANGUAGES as formatted
        names = dict((k, label) for k, label, _ in settings_mod.SPOKEN_LANGUAGES)
        skipped = [names[k] for k in self._settings.get("languages", []) if k not in formatted and k in names]
        if not skipped:
            return ""
        listed = skipped[0] if len(skipped) == 1 else ", ".join(skipped[:-1]) + " and " + skipped[-1]
        return f"It doesn't format {listed} yet: those dictations are pasted as you said them."

    @Property("QVariantList", constant=True)
    def historyOptions(self):
        return [{"days": -1 if d is None else d, "label": label} for d, label in settings_mod.HISTORY_OPTIONS]

    @Property("QVariantList", notify=settingsChanged)
    def mics(self):
        return [{"name": "", "label": "Windows default"}] + [{"name": n, "label": n} for n in self._mics]

    @Property(str, notify=settingsChanged)
    def hotkeyName(self):
        return settings_mod.HOTKEYS[self._settings["hotkey"]][1]

    @Property("QVariantList", notify=settingsChanged)
    def hotkeyKeys(self):
        """The hotkey as keycaps, e.g. ["Ctrl", "Win"]."""
        return [k.strip() for k in self.hotkeyName.split("+")]

    @Property(bool, notify=settingsChanged)
    def hotkeyIsCombo(self):
        return len(settings_mod.HOTKEYS[self._settings["hotkey"]][0]) > 1

    @Property(str, constant=True)
    def noiseUrl(self):
        return QUrl.fromLocalFile(str(brand.write_noise(settings_mod.APP_DIR / "grain.png"))).toString()

    # ------------------------------------------------------------------ called by app.py

    def set_listening(self, listening: bool) -> None:
        """Always call this, whether or not the window is visible (app.py)."""
        if listening != self._listening:
            self._listening = listening
            self.listeningChanged.emit()

    def set_mic_level(self, level: float) -> None:
        """Only call this while the window is visible (app.py): no point animating a hidden logo."""
        if abs(level - self._mic_level) > 0.002:
            self._mic_level = level
            self.micLevelChanged.emit()

    def set_live(self, listening: bool, level: float) -> None:
        """Convenience for preview scripts (render_gallery.py, render_window.py): sets both at once."""
        self.set_listening(listening)
        self.set_mic_level(level)

    def set_loading(self, loading: bool, loaded_ok: bool = False) -> None:
        """loading: the speech model is (re)loading. loaded_ok: it finished successfully (-> progress 1)."""
        progress = 1.0 if (not loading and loaded_ok) else 0.0
        if loading != self._loading or progress != self._load_progress:
            self._loading, self._load_progress = loading, progress
            self.loadingChanged.emit()

    def set_ai_formatting(self, state: str, message: str) -> None:
        if (state, message) != (self._ai_state, self._ai_message):
            self._ai_state, self._ai_message = state, message
            self.aiFormattingChanged.emit()

    def set_welcome_open(self, open_: bool) -> None:
        if open_ != self._welcome_open:
            self._welcome_open = open_
            if not open_:
                self.mic_test.stop()
            self.welcomeChanged.emit()

    def set_speech_model(self, state: dict) -> None:
        if state != self._speech_model:
            self._speech_model = dict(state)
            self.speechModelChanged.emit()

    def set_status(self, status: str, blocked: int | None = None) -> None:
        self._status = status
        if blocked is not None:
            self._blocked = blocked
        self.statusChanged.emit()

    def add_entry(self, entry_id: int) -> None:
        row = self.history.get(entry_id)
        if row:
            self.model.prepend(row)
        self.refresh_stats()

    def refresh_stats(self) -> None:
        self._stats = self.history.stats()
        self.statsChanged.emit()

    def set_mics(self, names: list[str]) -> None:
        self._mics = names
        self.settingsChanged.emit()

    def set_reduced_motion(self, reduced: bool) -> None:
        if reduced != self._reduced_motion:
            self._reduced_motion = reduced
            self.appearanceChanged.emit()

    # ------------------------------------------------------------------ slots for QML

    @Slot(str, "QVariant")
    def setSetting(self, key: str, value) -> None:
        if isinstance(value, QJSValue):  # a JS array from QML (the languages multi-select) arrives unconverted
            value = value.toVariant()
        if key == "history_days" and value == -1:
            value = None
        if key == "mic" and value == "":
            value = None
        if key == "accent" and value not in brand.ACCENTS:
            log.warning("ignored unknown accent %r", value)
            return
        if key == "languages":
            value = settings_mod.normalize_languages(list(value) if isinstance(value, (list, tuple)) else value)
            if value is None:           # empty or unknown: at least one language stays chosen
                log.warning("ignored an invalid languages choice")
                return
        if key == "language":           # the old single setting (older callers): becomes a languages list
            if value not in dict(settings_mod.LANGUAGES):
                return
            key, value = "languages", settings_mod.normalize_languages(settings_mod.FROM_LEGACY[value])
        if self._settings.get(key) == value:
            return
        self._settings[key] = value
        if key == "theme":  # the v2 theme picker, until it's gone: its accent replaces it
            self._settings["accent"] = brand.accent_for(value)
        # Every language but English needs a model that understands it (only "Most accurate" does),
        # so keep the languages and the model compatible. The Settings page says so in that group's
        # footer, where the change happened, so no toast.
        presets = settings_mod.MODEL_PRESETS
        if key == "languages":
            self._settings["language"] = settings_mod.legacy_language(value)  # for an older copy (settings.py)
            if settings_mod.needs_multilingual(value) and not presets[self._settings["preset"]]["multilingual"]:
                self._settings["preset"] = "accurate"
                self.settingEdited.emit("preset")
        elif key == "preset" and not presets[value]["multilingual"] \
                and settings_mod.needs_multilingual(self._settings["languages"]):
            self._settings["languages"], self._settings["language"] = ["en"], "en"
            self.settingEdited.emit("languages")
        settings_mod.save(self._settings)
        self.settingsChanged.emit()
        self.settingEdited.emit(key)

    @Slot(str)
    def search(self, query: str) -> None:
        self.model.reload(query)

    @Slot(int)
    def copyText(self, entry_id: int) -> None:
        row = self.history.get(entry_id)
        if row:
            QGuiApplication.clipboard().setText(row["text"])  # you asked to copy: a normal clipboard entry

    @Slot(int)
    def deleteEntry(self, entry_id: int) -> None:
        row = self.history.get(entry_id)
        if not row:
            return
        self.model.remove(entry_id)
        self.history.delete(entry_id)
        self._deleted = row
        self.refresh_stats()
        self.toast.emit("Dictation deleted", True)

    @Slot()
    def undoDelete(self) -> None:
        row, self._deleted = self._deleted, None
        if row:
            new_id = self.history.add(row["text"], row["raw_text"], row["audio_s"], row["app"], row["outcome"],
                                      row["latency_ms"], row["model"], created_at=row["created_at"],
                                      app_path=row.get("app_path") or "", language=row.get("language") or "",
                                      original_text=row.get("original_text"), formatting=row.get("formatting") or "")
            self.model.reload()
            self.refresh_stats()
            log.info("restored deleted dictation as #%d", new_id)

    @Slot()
    def clearHistory(self) -> None:
        self.history.clear()
        self.model.reload()
        self.refresh_stats()
        self.toast.emit("History deleted", False)

    @Slot(str, str)
    def addWord(self, term: str, heard: str) -> None:
        term, heard = term.strip(), heard.strip()
        if not term:
            return
        words = [w for w in self._settings["dictionary"] if w["term"].lower() != term.lower()]
        self.setSetting("dictionary", [{"term": term, "heard": heard}] + words)

    @Slot(int)
    def removeWord(self, index: int) -> None:
        words = list(self._settings["dictionary"])
        if 0 <= index < len(words):
            del words[index]
            self.setSetting("dictionary", words)

    @Slot(int, str, str)
    def updateWord(self, index: int, term: str, heard: str) -> None:
        term, heard = term.strip(), heard.strip()
        words = list(self._settings["dictionary"])
        if not term or not (0 <= index < len(words)):
            return
        if any(i != index and w["term"].lower() == term.lower() for i, w in enumerate(words)):
            return  # another entry already claims this term
        words[index] = {"term": term, "heard": heard}
        self.setSetting("dictionary", words)

    @Slot(str, str)
    def addSnippet(self, trigger: str, text: str) -> None:
        trigger = trigger.strip()
        if not trigger or not text.strip():
            return
        snippets = [s for s in self._settings["snippets"] if s["trigger"].lower() != trigger.lower()]
        self.setSetting("snippets", [{"trigger": trigger, "text": text}] + snippets)

    @Slot(int)
    def removeSnippet(self, index: int) -> None:
        snippets = list(self._settings["snippets"])
        if 0 <= index < len(snippets):
            del snippets[index]
            self.setSetting("snippets", snippets)

    @Slot(int, str, str)
    def updateSnippet(self, index: int, trigger: str, text: str) -> None:
        trigger, text = trigger.strip(), text.strip()
        snippets = list(self._settings["snippets"])
        if not trigger or not text or not (0 <= index < len(snippets)):
            return
        if any(i != index and s["trigger"].lower() == trigger.lower() for i, s in enumerate(snippets)):
            return  # another entry already claims this trigger
        snippets[index] = {"trigger": trigger, "text": text}
        self.setSetting("snippets", snippets)

    @Slot()
    def resume(self) -> None:
        """Resume from pause. app.py only acts on this while actually paused."""
        self.resumeRequested.emit()

    @Slot()
    def showWelcome(self) -> None:
        """Settings › General › Welcome: the first-run welcome again."""
        self.set_welcome_open(True)

    @Slot(bool, int)
    def finishWelcome(self, skipped: bool, step: int) -> None:
        """Finished, skipped (Esc, Skip) or the window closed: it's seen, and never shows by itself again."""
        log.info("welcome %s at step %d", "skipped" if skipped else "finished", step + 1)
        if welcome.mark_seen(self._settings):
            settings_mod.save(self._settings)
        self.set_welcome_open(False)

    @Slot()
    def toggleMicTest(self) -> None:
        self.mic_test.toggle()

    @Slot()
    def stopMicTest(self) -> None:
        self.mic_test.stop()

    @Slot()
    def downloadModel(self) -> None:
        self.downloadRequested.emit()

    @Slot()
    def cancelDownload(self) -> None:
        self.downloadCancelRequested.emit()

    @Slot()
    def openLogs(self) -> None:
        os.startfile(settings_mod.APP_DIR / "logs")


# ------------------------------------------------------------------ the native caption (DWM)

_dwm = ctypes.WinDLL("dwmapi")
_dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
_dwm.DwmSetWindowAttribute.restype = ctypes.c_long  # HRESULT
_uxtheme = ctypes.WinDLL("uxtheme")
_uxtheme.SetWindowThemeAttribute.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
_uxtheme.SetWindowThemeAttribute.restype = ctypes.c_long
# dwmapi.h / uxtheme.h (Windows 11 22000+)
DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR = 20, 34, 35, 36
DWMWA_COLOR_DEFAULT = 0xFFFFFFFF
WTA_NONCLIENT, WTNCA_NODRAWCAPTION, WTNCA_NODRAWICON = 1, 0x1, 0x2


class _WtaOptions(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD), ("dwMask", wintypes.DWORD)]


def colorref(hex_: str) -> int:
    """"#RRGGBB" -> a Win32 COLORREF (0x00BBGGRR). Opaque colours only: DWM has no alpha, and an
    "#AARRGGBB" token read as RGB is how the window border once turned cyan (#16FFFFFF -> #16FFFF)."""
    if not isinstance(hex_, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_):
        raise ValueError(f"DWM needs an opaque #RRGGBB colour, not {hex_!r}")
    return int(hex_[1:3], 16) | int(hex_[3:5], 16) << 8 | int(hex_[5:7], 16) << 16


def style_caption(hwnd: int) -> None:
    """The native caption and border in the current tokens.

    Keeps snap layouts, resize and the system buttons; the caption melts into the sidebar.
    Under a contrast theme the system's own frame colours come back.
    """
    t = brand.current()

    def put(attr: int, value: int) -> None:
        v = wintypes.DWORD(value)
        if _dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)):
            log.debug("DwmSetWindowAttribute(%d) failed", attr)

    put(DWMWA_USE_IMMERSIVE_DARK_MODE, t["mode"] == "dark")
    if t["highContrast"]:
        for attr in (DWMWA_CAPTION_COLOR, DWMWA_BORDER_COLOR, DWMWA_TEXT_COLOR):
            put(attr, DWMWA_COLOR_DEFAULT)
    else:
        put(DWMWA_CAPTION_COLOR, colorref(t["bgWindow"]))
        put(DWMWA_BORDER_COLOR, colorref(brand.WINDOW_BORDER[t["mode"]]))
        put(DWMWA_TEXT_COLOR, colorref(t["textSecondary"]))  # the caption title, if shown, stays quiet
    if HIDE_CAPTION_TITLE:
        # The window title stays "Vocet" for the taskbar, Alt+Tab and screen readers.
        opts = _WtaOptions(WTNCA_NODRAWCAPTION | WTNCA_NODRAWICON, WTNCA_NODRAWCAPTION | WTNCA_NODRAWICON)
        _uxtheme.SetWindowThemeAttribute(hwnd, WTA_NONCLIENT, ctypes.byref(opts), ctypes.sizeof(opts))


class VocetWindow:
    def __init__(self, backend: Backend):
        self.backend = backend
        self.engine = QQmlApplicationEngine()
        self.engine.warnings.connect(lambda ws: [log.warning("QML: %s", w.toString()) for w in ws])
        ctx = self.engine.rootContext()
        ctx.setContextProperty("theme", brand.current())
        ctx.setContextProperty("backend", backend)
        self.engine.addImageProvider("appicon", AppIconProvider())
        self.engine.load(QUrl.fromLocalFile(str(UI_DIR / "Main.qml")))
        if not self.engine.rootObjects():
            raise RuntimeError("Main.qml failed to load (see log)")
        self.window = self.engine.rootObjects()[0]
        self.window.setIcon(brand.window_icon())
        self._hwnd = 0  # the native window, once show() has created it
        self._greeted = False  # greet() fires once per session, on the first show()
        self._opened = False   # the first show() opens the window maximised; later ones keep its state

    def is_visible(self) -> bool:
        return bool(self.window) and self.window.isVisible()

    def hwnd(self) -> int:
        """The native window (0 until the first show()): app.py tells a dictation into Vocet's own
        window (the welcome's "Try it") from one into another app."""
        return self._hwnd

    def refresh_theme(self) -> None:
        """Re-publish the tokens after the accent, Windows' light/dark, Text size or contrast theme
        changed. Every QML binding that reads `theme` updates; the caption and icon follow."""
        self.engine.rootContext().setContextProperty("theme", brand.current())
        self.window.setIcon(brand.window_icon())
        if self._hwnd:
            style_caption(self._hwnd)
        self.backend.appearanceChanged.emit()

    def show(self, page: str | None = None) -> None:
        if page:
            self.window.setProperty("page", page)
        if not self._hwnd:  # create the native window first, so it never flashes the default caption
            self._hwnd = int(self.window.winId())
            style_caption(self._hwnd)
        if not self._greeted:
            self._greeted = True
            # Before show(), so the opening mark is already loaded for the very first frame and the
            # page never flashes underneath it. A direct call: the Loader loads synchronously.
            # invokeMethod is a no-op (not an error) if Main.qml has no greet() function.
            QMetaObject.invokeMethod(self.window, "greet")
        if not self._opened:
            # Maximised, not full screen: the title bar and taskbar stay. Closing only hides the window,
            # and Qt keeps its state, so the tray and Start menu bring it back as the user left it
            # (restored or resized stays so until the next start).
            self._opened = True
            self.window.showMaximized()
        else:
            self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    def close(self) -> None:
        """Delete the QML engine before the backend it reads from, so QML never sees a
        half-destroyed backend while shutting down."""
        self.window.setProperty("allowClose", True)
        self.window.close()
        self.engine.deleteLater()
        self.engine = None
