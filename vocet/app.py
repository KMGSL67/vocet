"""Vocet: hold a key, speak, let go, and your words appear where you're typing.

Threads, and why:
- Main (Qt) thread: keyboard hook, pill animation, window, tray. It must never
  block, or the pill stutters and Windows drops the keyboard hook.
- One worker thread (a single-worker executor): model loading, transcription,
  pasting. One worker = jobs run one at a time; they can never overlap.
- AI formatting (ai_format.py) has its own thread for the model; the worker waits
  for it at most a fixed time per dictation, then pastes the original.
- A short-lived thread per key press opens the microphone: a built-in laptop
  mic can take most of a second to open, and the pill must show at once. Only one is
  ever in flight (MicOpening); a press while one is still opening reuses it.
Workers report back through Qt signals, which Qt delivers on the main thread.

Test mode (VOCET_TEST_WAV=path.wav): the mic is replaced by that file and
synthetic key presses are accepted, so an end-to-end test can drive the whole
app. Never set in normal use.
"""

import contextlib
import ctypes
import logging
import logging.handlers
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import ai_format, audio, brand, insertion, privacy, settings as settings_mod, textproc, welcome
from .history import History
from .hotkey import PushToTalkKey
from .pill import Pill
from .sounds import Sounds
from .state import State, StateMachine

APP_DIR = settings_mod.APP_DIR


def _user_sid() -> str:
    """This process's Windows account SID ("S-1-5-21-..."), or "" if Windows won't say."""
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                 ctypes.POINTER(wintypes.DWORD)]
        advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
            return ""
        try:
            size = wintypes.DWORD()
            advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # 1 = TokenUser
            buf = ctypes.create_string_buffer(size.value)
            if not advapi32.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
                return ""
            psid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]   # TOKEN_USER.User.Sid
            text = wintypes.LPWSTR()
            if not advapi32.ConvertSidToStringSidW(psid, ctypes.byref(text)):
                return ""
            try:
                return text.value or ""
            finally:
                kernel32.LocalFree(text)
        finally:
            kernel32.CloseHandle(token)
    except (OSError, AttributeError, ValueError):
        return ""


def _session_id() -> int:
    sid = wintypes.DWORD()
    try:
        if ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(sid)):
            return sid.value
    except (OSError, AttributeError):
        pass
    return 0


def _home_tag(home: str) -> str:
    """A short, stable tag for a test data folder (the same folder always gives the same tag)."""
    import hashlib
    return hashlib.sha256(os.path.normcase(os.path.abspath(home)).encode("utf-8")).hexdigest()[:10]


def instance_name(sid: str | None = None, session: int | None = None, test: bool | None = None,
                  home: str | None = None) -> str:
    """The single-instance pipe (and mutex) name: per Windows account and per session, so another
    account can't squat it and fast user switching gives each user their own Vocet.
    Only letters, digits and dashes (a SID is "S-1-5-21-...").
    A test instance's name also carries its data folder's tag, so test runs in different folders
    never find (and replace) each other; two copies in the same folder still do."""
    sid = _user_sid() if sid is None else sid
    session = _session_id() if session is None else session
    home = os.environ.get("VOCET_HOME", "") if home is None else home
    test = bool(home) if test is None else test
    who = re.sub(r"[^0-9A-Za-z-]", "", sid) or re.sub(r"[^0-9A-Za-z-]", "", os.environ.get("USERNAME", "")) or "user"
    return f"VocetPublicInstance-{who}-s{session}" + (f"-test-{_home_tag(home)}" if test else "")


INSTANCE_NAME = instance_name()
MIN_HOLD_S = 0.3          # shorter presses are taps, not dictation
DOUBLE_TAP_S = 0.45       # two taps within this = hands-free
MAX_RECORDING_S = 300     # safety stop
MIC_SLOW_NOTICE_S = 0.3   # let go while the mic was still starting after at least this long: say why
MIC_OPEN_WAIT_S = 2.0     # quitting waits at most this long for a microphone that's still opening
MSG_MIC_SLOW = "The mic took a moment to start. Hold the keys a bit longer."
# The first load compiles the model for this PC's chip (engines.prepare). It starts with "Loading"
# so the sidebar shows it as loading, and it fits the pill and the sidebar's two lines.
MSG_FIRST_LOAD = "Loading the speech model. The first time takes up to a minute."
GPU_WAIT_S = 1.0          # transcription waits at most this long for the formatter to leave the GPU
TEST_WAV = os.environ.get("VOCET_TEST_WAV")


def code_version() -> str:
    """A fingerprint of Vocet's own code (every .py/.qml file's size and modification time).

    Opening Vocet while an *older* copy is still running must give you the new code:
    the running copy compares fingerprints and steps aside if they differ (see
    _hand_over). VOCET_CODE_VERSION overrides it, for the test of exactly that.
    """
    import hashlib
    if os.environ.get("VOCET_CODE_VERSION"):
        return os.environ["VOCET_CODE_VERSION"]
    root = Path(__file__).resolve().parent
    digest = hashlib.sha1()
    for f in sorted(list(root.rglob("*.py")) + list(root.rglob("*.qml"))):
        st = f.stat()
        digest.update(f"{f.relative_to(root)}:{st.st_size}:{st.st_mtime_ns}".encode())
    return digest.hexdigest()[:12]


VERSION = code_version()

log = logging.getLogger("vocet")

FRIENDLY_APPS = {
    "winword.exe": "Word", "excel.exe": "Excel", "powerpnt.exe": "PowerPoint", "outlook.exe": "Outlook",
    "olk.exe": "Outlook", "onenote.exe": "OneNote", "ms-teams.exe": "Teams", "teams.exe": "Teams",
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox", "code.exe": "VS Code",
    "cursor.exe": "Cursor", "notepad.exe": "Notepad", "windowsterminal.exe": "Terminal",
    "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell", "cmd.exe": "Command Prompt",
    "discord.exe": "Discord", "slack.exe": "Slack", "whatsapp.exe": "WhatsApp", "notion.exe": "Notion",
    "obsidian.exe": "Obsidian", "explorer.exe": "File Explorer", "pythonw.exe": "Vocet", "python.exe": "Vocet",
}


def setup_logging() -> None:
    """Local log file only. Timings and errors, never the dictated text, clipboard contents or
    window titles. privacy.RedactingFormatter takes the user name out of paths and tracebacks."""
    import atexit
    import faulthandler

    (APP_DIR / "logs").mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(APP_DIR / "logs" / "vocet.log",
                                                   maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(privacy.RedactingFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # Uncaught exceptions can come from code that holds your words: log where, not the message.
    sys.excepthook = lambda *exc: log.critical("uncaught exception", exc_info=exc,
                                               extra={privacy.NO_EXC_MESSAGE: True})
    # A native crash (in Qt, OpenVINO, a driver...) can't be caught by Python; faulthandler at
    # least writes where it happened. pythonw has no console, so it goes to a file. It bypasses
    # the formatter, so the previous run's crash.log is redacted (and trimmed) at start-up.
    global _crash_file
    privacy.tidy_crash_log(APP_DIR / "logs" / "crash.log")
    _crash_file = open(APP_DIR / "logs" / "crash.log", "a", encoding="utf-8")
    faulthandler.enable(_crash_file)
    atexit.register(lambda: log.info("process exiting"))


_crash_file = None


@contextlib.contextmanager
def gpu_turn(lock, wait_s: float = GPU_WAIT_S):
    """Transcription and the formatter take turns on the GPU (together both get slower).
    Never waits long: a formatter stuck in a driver mustn't cost a dictation."""
    got = lock.acquire(timeout=wait_s)
    try:
        yield got
    finally:
        if got:
            lock.release()


def app_of(hwnd: int) -> tuple[str, str]:
    """(name, program path) behind a window, e.g. ("Word", "C:\\...\\WINWORD.EXE").
    The path is only used to show the program's icon. Never the window title (privacy)."""
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        proc = psutil.Process(pid.value)
        exe, path = proc.name(), proc.exe()
    except (psutil.Error, ValueError, OSError):
        return "", ""
    return FRIENDLY_APPS.get(exe.lower(), Path(exe).stem.replace("_", " ").title()), path


def _new_recorder(mic: str | None):
    """A recorder for the chosen mic (or the test WAV). Opening a real one can take most of a
    second on a built-in laptop mic, so a dictation does this on its own thread."""
    return audio.WavRecorder(TEST_WAV) if TEST_WAV else audio.Recorder(audio.find_input_device(mic))


class MicOpening:
    """One microphone being opened on its own thread, for a key press.

    The Qt thread decides what happens when it arrives: `wanted` (a press is waiting for it, it
    becomes the recording) or not (you let go meanwhile: it's closed at once). `lock` guards the
    hand-over of `recorder` between the opening thread, the Qt thread and quit()."""

    def __init__(self, mic: str | None):
        self.mic = mic
        self.wanted = True
        self.recorder = None
        self.open_ms = self.start_ms = 0.0
        self.abandoned = False            # Vocet is quitting: the thread closes whatever it opens
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None

    def take(self):
        """The opened recorder, now the caller's (None if it isn't there or was taken already)."""
        with self.lock:
            rec, self.recorder = self.recorder, None
        return rec


def _close_quietly(rec) -> None:
    try:
        rec.close()
    except Exception:
        log.exception("closing microphone")


class Signals(QObject):
    loaded = Signal(object)          # Transcriber
    load_failed = Signal(str)
    inserting = Signal()
    pasted = Signal()                # Ctrl+V sent (clipboard restore still pending)
    finished = Signal(dict)          # result of one dictation
    failed = Signal(str)
    ai_state = Signal(str, str)      # AI formatting: state, the sentence for Settings
    mic_ready = Signal(object)       # MicOpening: the stream runs
    mic_failed = Signal(object)      # MicOpening: the microphone didn't open


class VocetApp:
    def __init__(self, qt: QApplication, guard: privacy.NetworkGuard):
        from .window import Backend, VocetWindow, SystemAppearance  # QML is only imported once Qt is running

        self.qt = qt
        self.guard = guard
        self.settings = settings_mod.load()
        self.system = SystemAppearance()  # Windows' light/dark, Text size, Animation effects, contrast theme
        self._apply_tokens()              # before anything draws
        self.history = History(APP_DIR / "history.db")
        self.history.prune(self.settings["history_days"])
        if welcome.migrate(self.settings, bool(self.history.recent(limit=1))):
            settings_mod.save(self.settings)  # you've dictated before: no welcome
        self.sm = StateMachine()
        self.signals = Signals()
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.transcriber = None
        self.recorder = None
        self._mic_job = None          # MicOpening: a microphone opening on its own thread
        self.target_window = 0
        self.pressed_at = 0.0
        self.last_tap_at = 0.0
        self.locked = False           # hands-free recording in progress
        self._reload_pending = False  # model preset changed while busy
        self.ai = ai_format.AiFormatting(on_change=lambda state, message: self.signals.ai_state.emit(state, message))
        self._ai_started = False      # starts once the speech model has loaded (they share the GPU)
        self.sounds = Sounds(APP_DIR / "sounds")
        self.sounds.enabled = self.settings["sounds"]

        self.pill = Pill()
        self.pill.reduced = self.system.reduced_motion
        self.pill.show_idle = self.settings["show_idle"]
        self.pill.level_source = self._pill_level
        self.key = PushToTalkKey(self._hotkey_groups(), test_mode=bool(TEST_WAV))
        self.key.pressed.connect(self.on_press)
        self.key.released.connect(self.on_release)
        self.key.cancelled.connect(self.on_cancel)
        self.key.escape.connect(lambda: self._discard("Esc", sound=True))
        self.key.hands_free.connect(self.on_hands_free)
        self.max_timer = QTimer(singleShot=True, timeout=self._finish_recording)
        self.live_timer = QTimer(interval=33, timeout=self._push_live_level)  # window logo follows your voice

        s = self.signals
        s.loaded.connect(self._on_loaded)
        s.load_failed.connect(self._on_load_failed)
        s.inserting.connect(lambda: self.sm.go(State.INSERTING))
        s.pasted.connect(lambda: self.pill.set_mode("done"))
        s.finished.connect(self._on_finished)
        s.failed.connect(self._on_failed)
        s.ai_state.connect(self._on_ai_state)
        s.mic_ready.connect(self._on_mic_ready)
        s.mic_failed.connect(self._on_mic_failed)

        self.backend = Backend(self.settings, self.history)
        self.backend.settingEdited.connect(self._on_setting_edited)
        self.backend.resumeRequested.connect(self._on_resume_requested)
        self.backend.set_mics([d["name"] for d in audio.list_input_devices()])
        self.backend.mic_test.opener = self._open_mic   # the welcome's "Test microphone"
        self.backend.downloadRequested.connect(self._start_download)
        self.backend.downloadCancelRequested.connect(self._cancel_download)
        self.downloader = None        # model_download.Downloader, made when a model is missing
        self._model_missing = False
        self.window = VocetWindow(self.backend)
        self.system.changed.connect(self._on_system_appearance)

        self.tray = QSystemTrayIcon()
        self._set_tray("loading")
        self.tray.setToolTip("Vocet: loading the speech model…")
        self.tray.activated.connect(self._on_tray_activated)
        self._build_menu()
        self.tray.show()

        self.server = QLocalServer()  # opening Vocet again talks to this running copy (see _hand_over)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)  # only your own account
        self.server.newConnection.connect(self._on_second_launch)
        self._listen()
        insertion.prepare_password_check()  # starts UI Automation now, so the first paste doesn't wait for it
        self.prune_timer = QTimer(interval=3600_000, timeout=self._prune)
        self.prune_timer.start()

    def _prune(self) -> None:
        self.history.prune(self.settings["history_days"])

    def _pill_level(self) -> float:
        return self.recorder.level if self.recorder else 0.0

    def _listen(self, attempt: int = 1) -> None:
        """Opens the single-instance pipe. If that fails, Vocet still runs (the mutex keeps it
        the only copy), but opening it again can't reach it, so say so and retry a few times."""
        QLocalServer.removeServer(INSTANCE_NAME)
        if self.server.listen(INSTANCE_NAME):
            return
        log.warning("single-instance pipe unavailable (attempt %d: %s); opening Vocet again can't reach this copy",
                    attempt, self.server.errorString())
        if attempt < 3:
            QTimer.singleShot(2000 * attempt, lambda: self._listen(attempt + 1))

    def _on_second_launch(self) -> None:
        """Vocet was opened again. Same code: show the window. Newer code: step aside.

        Reads on readyRead instead of blocking: the keyboard hook lives on this thread, and a
        client that connects and says nothing must not stall it."""
        while (sock := self.server.nextPendingConnection()) is not None:
            state = {"done": False}
            sock.readyRead.connect(lambda s=sock, st=state: self._on_hello(s, st))
            QTimer.singleShot(500, lambda s=sock, st=state: self._on_hello(s, st, timed_out=True))

    def _on_hello(self, sock, state: dict, timed_out: bool = False) -> None:
        """Only a well-formed hello from a real Vocet process can make this copy quit."""
        if state["done"]:
            return
        message = bytes(sock.readAll())
        if not message and not timed_out:
            return
        state["done"] = True
        their_version = parse_hello(message)
        if their_version and their_version != VERSION and _pipe_client_is_vocet(sock):
            log.info("a newer Vocet (%s) was opened; this one (%s) steps aside", their_version, VERSION)
            sock.write(b"restarting")
            sock.flush()
            sock.waitForBytesWritten(500)
            QTimer.singleShot(100, self.quit)
        else:
            if their_version and their_version != VERSION:
                log.warning("a different version said hello, but not from a Vocet process; not stepping aside")
            elif message and not their_version:
                log.warning("unexpected message on the single-instance pipe (%d bytes); ignored", len(message))
            sock.write(b"ok")
            sock.flush()
            self.window.show()
        sock.disconnected.connect(sock.deleteLater)
        if sock.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            sock.deleteLater()

    def _hotkey_groups(self):
        return settings_mod.HOTKEYS[self.settings["hotkey"]][0]

    def _hotkey_name(self) -> str:
        return settings_mod.HOTKEYS[self.settings["hotkey"]][1]

    # ------------------------------------------------------------------ startup / model

    def start(self) -> None:
        self.pill.start()
        self.key.install()
        if self._check_model():
            self.pill.set_mode("loading", "Loading the speech model")
            self._load_model()
        if welcome.should_show(self.settings, test_mode=bool(TEST_WAV)):
            self.backend.set_welcome_open(True)   # before show(): it's there from the first frame
            self.window.show()                    # first run: the welcome, right after the opening

    # ------------------------------------------------------------------ the speech model's download

    def _preset(self) -> dict:
        return settings_mod.MODEL_PRESETS[self.settings["preset"]]

    def _check_model(self) -> bool:
        """True if a speech model for the current preset is on this PC. If not, nothing loads and
        the welcome / Settings offer the download (it never starts by itself)."""
        from . import engines, hardware, model_download
        preset = self._preset()
        attempts = hardware.plan(preset, self.settings["languages"])
        if any(engines.is_downloaded(a.engine, a.model) for a in attempts):
            self._model_missing = False
            if not (self.downloader and self.downloader.running):
                self.backend.set_speech_model({"state": "ready"})
            return True
        self._model_missing = True
        try:
            p = model_download.plan(preset["engine"], preset["model"])
        except Exception as exc:  # noqa: BLE001 - not pinned: can't be downloaded safely
            log.error("the speech model is missing and can't be downloaded: %s", exc)
            self.backend.set_speech_model({"state": "failed", "message": hardware.MSG_FAILED})
            self.backend.set_status("Speech model not downloaded")
            return False
        if self.downloader is None or self.downloader.plan.key != p.key:
            if self.downloader is not None:
                self.downloader.cancel()
            self.downloader = model_download.Downloader(p, guard=self.guard)
            self.downloader.changed.connect(self._on_download_state)
            self.downloader.finished.connect(self._on_download_finished)
        self.backend.set_speech_model(self.downloader.state)
        self.backend.set_status("Speech model not downloaded")
        self.backend.set_loading(False)
        log.info("speech model %s isn't on this PC (%s): offering the download", p.key,
                 model_download.size_label(p.total))
        return False

    def _start_download(self) -> None:
        if self.downloader and self._model_missing and self.downloader.start():
            log.info("model download started (you asked for it)")

    def _cancel_download(self) -> None:
        if self.downloader:
            self.downloader.cancel()

    def _on_download_state(self, state: dict) -> None:
        self.backend.set_speech_model(state)
        if state["state"] == "downloading":
            self.backend.set_status(f"Downloading the speech model, {round(100 * state['progress'])} %")
        elif state["state"] == "verifying":
            self.backend.set_status("Checking the speech model")
        elif state["state"] in ("failed", "cancelled"):
            self.backend.set_status("Speech model not downloaded")

    def _on_download_finished(self, ok: bool) -> None:
        if ok:
            log.info("network: %d connections to Hugging Face during the download", len(self.guard.allowed))
        if ok and self._check_model():
            self.pill.set_mode("loading", "Loading the speech model")
            self._load_model()

    def _open_mic(self):
        """The recorder for the welcome's microphone test: the chosen mic (or the test WAV)."""
        return _new_recorder(self.settings["mic"])

    def _load_model(self) -> None:
        preset = settings_mod.MODEL_PRESETS[self.settings["preset"]]
        if self._first_compile(preset):   # the pill and the sidebar say why this one takes longer
            self.pill.set_mode("loading", MSG_FIRST_LOAD)
            self.backend.set_status(MSG_FIRST_LOAD)
        else:
            self.backend.set_status("Loading the speech model")
        self.backend.set_loading(True)
        self.worker.submit(self._load_model_job, preset, [w["term"] for w in self.settings["dictionary"]])

    def _first_compile(self, preset: dict) -> bool:
        """The model hasn't been compiled for this PC's chip yet (a new install, a new OpenVINO or
        an emptied cache), so this load takes up to a minute instead of a few seconds. Cheap: the
        plan only looks at file sizes, and engines.is_prepared reads one small file."""
        from . import engines, hardware
        try:
            first = hardware.plan(preset, self.settings["languages"])[0]
            return not engines.is_prepared(first.engine, first.model, first.device, first.threads)
        except Exception:  # noqa: BLE001 - only the wording depends on it
            log.exception("couldn't tell whether the speech model was compiled before")
            return False

    def _load_model_job(self, preset: dict, words: list[str]) -> None:
        """Worker thread. Tries the preset's own chip, then the others, then the processor."""
        from . import hardware
        from .speech import Transcriber
        try:
            if self.transcriber:
                self.transcriber.close()
                self.transcriber = None
            languages = list(self.settings["languages"])   # what this load plans for (see _on_loaded)
            attempts = hardware.plan(preset, languages)
            loaded = hardware.load(attempts, lambda a: Transcriber(a.engine, a.model, a.device, a.threads))
            t = loaded.transcriber
            t.note = loaded.note          # one plain sentence if it fell back, else ""
            t.planned_languages = languages
            t.set_vocabulary(words)
            t.set_languages(languages)
            self.signals.loaded.emit(t)
        except hardware.LoadCancelled:
            log.info("speech model load stopped: Vocet is quitting")
        except hardware.LoadFailed as exc:
            log.error("no speech model could be loaded: %s", exc)
            self.signals.load_failed.emit(exc.user_message)
        except Exception:
            log.exception("model load failed")
            self.signals.load_failed.emit(hardware.MSG_FAILED)

    def _on_loaded(self, transcriber) -> None:
        self.transcriber = transcriber
        self.sm.go(State.IDLE)
        self.pill.set_mode("idle")
        self.backend.set_loading(False, loaded_ok=True)
        self._update_ready()
        note = getattr(transcriber, "note", "")
        if note:  # it fell back to another chip: say so once, in one sentence
            self.pill.set_mode("message", note, hold_ms=6000, kind="notice")
            self.backend.toast.emit(note, False)
        if not self._ai_started:  # after the speech model, so the two never compile on the GPU at once
            self._ai_started = True
            self.ai.check()
            if self.settings["ai_formatting"]:
                self.ai.set_enabled(True)
        # Languages changed while it loaded: the job planned with the list it saw when it started.
        planned = getattr(transcriber, "planned_languages", None)
        if planned is not None and list(planned) != list(self.settings["languages"]) \
                and not self._needs_multilingual_model():
            self.worker.submit(transcriber.set_languages, list(self.settings["languages"]))
        self._apply_pending_reload()   # or it needs another model for them now

    def _needs_multilingual_model(self) -> bool:
        """The loaded model is English-only (a processor fallback), but a language you speak isn't
        English and the preset itself is multilingual: another model has to load."""
        s = self.settings
        return bool(self.transcriber) and settings_mod.needs_multilingual(s["languages"]) \
            and not self.transcriber.multilingual and settings_mod.MODEL_PRESETS[s["preset"]]["multilingual"]

    def _apply_pending_reload(self) -> None:
        """A model change asked for while Vocet was busy, paused or loading applies once it's idle:
        a new preset, or a language the English-only fallback model can't write. Loop-free: the
        reload plans with the current languages, so it loads a multilingual model (or fails)."""
        if self.sm.state != State.IDLE:
            return
        if self._reload_pending:
            self._on_setting_edited("preset")
        elif self._needs_multilingual_model():
            self._on_setting_edited("languages")

    def _on_ai_state(self, state: str, message: str) -> None:
        self.backend.set_ai_formatting(state, message)
        if message == ai_format.MSG_PAUSED:  # it turned itself off: say so once
            self.backend.toast.emit(message, False)

    def _update_ready(self) -> None:
        self._set_tray("ready")
        self.tray.setToolTip(self._ready_tip())
        self.backend.set_status("Ready", blocked=len(self.guard.blocked))
        self.status_action.setText(f"Hold {self._hotkey_name()} to dictate")

    def _on_load_failed(self, message: str) -> None:
        self.sm.go(State.ERROR)
        from . import hardware
        message = message or hardware.MSG_FAILED
        self.pill.set_mode("message", message, hold_ms=6000, kind="warning")
        self.backend.toast.emit(message, False)   # the pill is painted, not readable by a screen reader; the pill may also cut it
        self.tray.setToolTip("Vocet: the speech model didn't load")
        self.backend.set_status("Speech model didn't load. Restart Vocet")
        self.backend.set_loading(False, loaded_ok=False)

    # ------------------------------------------------------------------ dictation

    def on_press(self) -> None:
        if self.sm.state == State.LISTENING and self.locked:
            self._finish_recording()  # hands-free: a tap finishes
            return
        if self.sm.state == State.STARTING:
            if self.locked:  # hands-free, and the tap to finish came before the mic was ready: nothing recorded
                self._cancel_starting("hands-free finished before the microphone was ready")
            return  # otherwise a second press while the mic is starting: ignored
        if self._model_missing:
            self.pill.set_mode("message", "Vocet needs its speech model first. Open Vocet to download it.", hold_ms=6000,
                               kind="warning")
            return
        if self.sm.state == State.LOADING:
            self.pill.set_mode("message", "Still loading the speech model.", hold_ms=4000, kind="notice")
            return
        if self.sm.state == State.ERROR and not self.transcriber:
            self.pill.set_mode("message", "The speech model didn't load. Restart Vocet to try again.", hold_ms=6000,
                               kind="warning")
            return
        if self.sm.state != State.IDLE:
            return  # busy or paused: ignore (never two jobs at once)
        # The whole chord is held (never on a single Ctrl). The mic opens on its own thread and
        # the pill shows now, in this same turn; "listening" and the start sound wait for the
        # stream, so the tick means "talk now".
        self.pressed_at = time.perf_counter()
        self.target_window = insertion.foreground_window()
        self.backend.mic_test.stop()  # a microphone test never runs under a dictation
        self.sm.go(State.STARTING)
        self.locked = False
        job = self._mic_job
        if job is None:
            job = self._mic_job = MicOpening(self.settings["mic"])
            job.thread = threading.Thread(target=self._open_mic_job, args=(job,), name="vocet-mic-open", daemon=True)
            job.thread.start()
        else:  # never two microphones: the one from a moment ago (a double-tap's first tap) is still opening
            log.info("the microphone from the previous press is still opening; using it")
        job.wanted = True
        self.key.listening = True  # Esc cancels from now on
        self.key.watch_release()   # a key-up the hook misses still ends it, while starting too
        self.pill.set_locked(False)
        self.pill.set_mode("starting")

    def _open_mic_job(self, job: MicOpening) -> None:
        """Its own short-lived thread: open and start the microphone, then hand it to the Qt thread."""
        t0 = time.perf_counter()
        rec = None
        try:
            rec = _new_recorder(job.mic)
            t1 = time.perf_counter()
            rec.start()
            t2 = time.perf_counter()
        except Exception:
            log.exception("microphone failed to open")
            if rec is not None:
                _close_quietly(rec)
            self.signals.mic_failed.emit(job)
            return
        job.open_ms, job.start_ms = (t1 - t0) * 1000, (t2 - t1) * 1000
        with job.lock:
            if not job.abandoned:
                job.recorder, rec = rec, None
        if rec is not None:  # Vocet quit while it was opening
            _close_quietly(rec)
            return
        self.signals.mic_ready.emit(job)

    def _on_mic_ready(self, job: MicOpening) -> None:
        if job is self._mic_job:
            self._mic_job = None
        rec = job.take()
        if rec is None:
            return  # quit() took it
        mic_ms = job.open_ms + job.start_ms
        if not job.wanted or self.sm.state != State.STARTING:
            _close_quietly(rec)
            log.info("the microphone opened after the press had ended (mic open in %.0f ms); closed it", mic_ms)
            return
        self.recorder = rec
        self.sm.go(State.LISTENING)
        self.pill.set_mode("listening")    # the dots take the accent: talk now
        self.backend.set_listening(True)   # always sent, whether or not the window is visible
        self.sounds.play("start")
        self.max_timer.start(MAX_RECORDING_S * 1000)
        self.live_timer.start()
        log.info("listening (mic open in %.0f ms: device %.0f + start %.0f; press to listening %.0f ms%s)",
                 mic_ms, job.open_ms, job.start_ms, (time.perf_counter() - self.pressed_at) * 1000,
                 ", hands-free" if self.locked else "")
        self._set_tray("listening")  # after the log line: drawing the icon isn't mic latency
        self.tray.setToolTip("Vocet: listening")

    def _on_mic_failed(self, job: MicOpening) -> None:
        if job is self._mic_job:
            self._mic_job = None
        if job.wanted and self.sm.state == State.STARTING:
            self._on_failed("Microphone unavailable. Check it's plugged in.")
        else:
            log.info("the microphone didn't open, but the press had already ended")

    def _cancel_starting(self, why: str, sound: bool = False, message: str = "") -> None:
        """Let go (or Esc, or a shortcut) before the mic was ready: nothing was recorded. The mic
        still opening is closed the moment it arrives, and nothing is ever inserted."""
        if self.sm.state != State.STARTING:
            return
        if self._mic_job is not None:
            self._mic_job.wanted = False
        self._stop_listening_ui()
        self.sm.go(State.IDLE)
        if message:
            self.pill.set_mode("message", message, hold_ms=4500, kind="notice")
        else:
            self.pill.set_mode("idle")
        if sound:
            self.sounds.play("cancel")
        log.info("cancelled while the microphone was starting: %s", why)

    def _go_hands_free(self, why: str) -> None:
        self.locked = True
        self.key.stop_watching()  # hands-free: the keys are meant to be let go
        self.pill.set_locked(True)
        log.info("hands-free on (%s)", why)

    def on_hands_free(self) -> None:
        """Space while holding the hotkey: keep listening after the keys are released."""
        if self.sm.state in (State.LISTENING, State.STARTING) and not self.locked and self.settings["hands_free"]:
            self._go_hands_free("Space" if self.sm.state == State.LISTENING else "Space, microphone still starting")

    def on_cancel(self) -> None:
        if self.sm.state in (State.LISTENING, State.STARTING) and not self.locked:
            self._discard("shortcut chord")

    def on_release(self) -> None:
        if self.locked or self.sm.state not in (State.LISTENING, State.STARTING):
            return
        now = time.perf_counter()
        held = now - self.pressed_at
        if held < MIN_HOLD_S:  # a tap, not dictation
            if self.settings["hands_free"] and now - self.last_tap_at < DOUBLE_TAP_S:
                # second quick tap: keep listening, hands-free (still starting: it listens once the mic is on)
                self._go_hands_free("double-tap" if self.sm.state == State.LISTENING
                                    else "double-tap, microphone still starting")
                return
            self.last_tap_at = now
            self._discard("tap", sound=False)
            return
        if self.sm.state == State.STARTING:  # held long enough, but let go before the mic was ready
            slow = held >= max(MIN_HOLD_S, MIC_SLOW_NOTICE_S)
            self._cancel_starting(f"let go after {held * 1000:.0f} ms, before the microphone was ready",
                                  message=MSG_MIC_SLOW if slow else "")
            return
        self._finish_recording()

    def _finish_recording(self) -> None:
        if self.sm.state != State.LISTENING:
            return
        self.max_timer.stop()
        clip = self.recorder.stop()
        first_audio = self.recorder.first_audio_latency_s
        self._stop_listening_ui()
        self.sm.go(State.PROCESSING)
        self.pill.set_mode("processing")
        self.sounds.play("stop")
        log.info("recorded %.2f s (first audio after %s ms)", audio.duration_s(clip),
                 f"{first_audio * 1000:.0f}" if first_audio else "?")
        s = self.settings
        rules = {"fillers": s["remove_fillers"], "snippets": s["snippets"],
                 "replacements": [{"heard": w["heard"], "write": w["term"]} for w in s["dictionary"] if w.get("heard")]}
        self.worker.submit(self._process, clip, self.target_window, time.perf_counter(), rules)

    def _process(self, clip, target_window: int, released_at: float, rules: dict) -> None:
        """Worker thread: transcribe, clean up, format, paste. Never touches the UI directly."""
        try:
            with gpu_turn(self.ai.gpu_lock):
                raw = self.transcriber.transcribe(clip)
            language = self.transcriber.detected
            text = textproc.process(raw, language=language, **rules) if raw else ""
            transcribed_at = time.perf_counter()
            app, app_path = app_of(target_window)
            original, formatting, format_ms, formatted = text, "off", 0.0, False
            if text and self.settings.get("ai_formatting") and insertion.focused_is_password() is not True:
                done = self.ai.format(text, language, app)   # at most ai_format.deadline_s(text); never raises
                text, formatting, format_ms, formatted = done.text, done.status, done.ms, done.formatted
            base = {"raw": raw, "text": text, "original": original, "formatting": formatting, "format_ms": format_ms,
                    "audio_s": audio.duration_s(clip), "app": app, "app_path": app_path, "language": language,
                    "transcribe_ms": (transcribed_at - released_at) * 1000, "model": self.transcriber.name}
            if not text:
                self.signals.finished.emit({**base, "outcome": "no_speech"})
                return
            if insertion.foreground_window() != target_window:
                # You switched windows while it was transcribing. Pasting now could land in
                # the wrong place, and the clipboard is yours: the text goes to History only.
                self.signals.finished.emit({**base, "outcome": "switched"})
                return
            self.signals.inserting.emit()
            try:
                result = insertion.insert_text(text, target_window, on_pasted=self.signals.pasted.emit,
                                               keep_lines=formatted and insertion.keeps_line_breaks(app_path))
            except insertion.FocusChanged:  # switched in the last moment before Ctrl+V
                self.signals.finished.emit({**base, "outcome": "switched"})
                return
            except insertion.PasswordField:  # not pasted, not kept anywhere
                self.signals.finished.emit({**base, "raw": "", "text": "", "original": "", "outcome": "password"})
                return
            outcome = "inserted" if result["read_confirmed"] else "unread"
            self.signals.finished.emit({**base, **result, "outcome": outcome,
                                        "total_ms": (result["pasted_at"] - released_at) * 1000})
        except Exception as exc:
            # The traceback without the exception's message: a message could quote your words.
            log.error("dictation failed", exc_info=exc, extra={privacy.NO_EXC_MESSAGE: True})
            self.signals.failed.emit("Another app is using the clipboard. Try again in a moment." if isinstance(exc, insertion.ClipboardBusy)
                                     else "That didn't work. Try again, or see Settings › Log files.")

    def _on_finished(self, r: dict) -> None:
        outcome = r["outcome"]
        history_on = self.settings["history_days"] != 0
        if outcome in ("inserted", "switched", "unread") and history_on:
            entry_id = self.history.add(r["text"], r["raw"], r["audio_s"], r["app"],
                                        "inserted" if outcome == "inserted" else "copied",  # "copied" = not pasted
                                        r.get("total_ms", r["transcribe_ms"]), r["model"], app_path=r["app_path"],
                                        language=r["language"], original_text=r.get("original"),
                                        formatting=r.get("formatting", "off"))
            self.backend.add_entry(entry_id)
        if outcome in ("inserted", "unread"):  # the welcome's "Try it" listens for its own field
            self.backend.dictated.emit(bool(self.target_window) and self.target_window == self.window.hwnd())
        # The clipboard is never used as a fallback: it's always restored.
        if outcome == "unread":
            log.info("the app didn't accept the paste; text kept in history: %s", history_on)
            self.pill.set_mode("message", "This app didn’t take the text. It’s saved in Vocet’s history." if history_on
                               else "This app didn’t take the text. History is off, so it wasn’t kept.",
                               hold_ms=6000, kind="warning")
        if outcome == "inserted":
            log.info("inserted: transcribe %.0f ms, AI formatting %s (%.0f ms), paste %.0f ms, app read it after "
                     "%.0f ms (confirmed %s), release->text %.0f ms, clipboard restored %s", r["transcribe_ms"],
                     r.get("formatting", "off"), r.get("format_ms", 0.0), r["paste_ms"], r["read_ms"],
                     r["read_confirmed"], r["total_ms"], r["restored"])
        elif outcome == "switched":
            log.info("focus changed before pasting; nothing pasted, text kept in history: %s", history_on)
            self.pill.set_mode("message", "You switched windows, so it’s saved in Vocet’s history." if history_on
                               else "You switched windows, so nothing was typed. History is off.",
                               hold_ms=6000, kind="notice")
        elif outcome == "password":
            log.info("focused field is a password field; nothing pasted or kept")
            self.pill.set_mode("message", "Vocet doesn’t type into password fields.", hold_ms=4500, kind="warning")
        elif outcome == "no_speech":
            log.info("no speech detected")
            self.pill.set_mode("message", "Didn’t hear anything. Check your microphone or speak up.", hold_ms=4500,
                               kind="notice")
        if self.sm.state in (State.PROCESSING, State.INSERTING):
            self.sm.go(State.IDLE)
        self._apply_pending_reload()  # a model change made mid-dictation applies now

    def _on_failed(self, message: str) -> None:
        self._stop_listening_ui()
        self.sm.go(State.ERROR)
        self.pill.set_mode("message", message, hold_ms=6000, kind="warning")
        self.backend.toast.emit(message, False)   # the pill isn't readable by a screen reader
        self.sounds.play("cancel")
        self.sm.go(State.IDLE)

    def _discard(self, why: str, sound: bool = False) -> None:
        if self.sm.state == State.STARTING:
            self._cancel_starting(why, sound=sound)
            return
        if self.sm.state != State.LISTENING:
            return
        self.max_timer.stop()
        if self.recorder:
            self.recorder.stop()
        self._stop_listening_ui()
        self.sm.go(State.IDLE)
        self.pill.set_mode("idle")
        if sound:
            self.sounds.play("cancel")
        log.info("discarded recording: %s", why)

    def _stop_listening_ui(self) -> None:
        self._close_recorder()
        self.locked = False
        self.pill.set_locked(False)
        self.key.listening = False
        self.key.stop_watching()
        self.live_timer.stop()
        self.backend.set_listening(False)  # always sent, whether or not the window is visible
        if self.window.is_visible():
            self.backend.set_mic_level(0.0)
        if self._tray_state == "listening":
            self._set_tray("ready")
            self.tray.setToolTip(self._ready_tip())

    def _push_live_level(self) -> None:
        # Mic-level updates are only worth sending to QML while the window is on screen;
        # the floating pill reads the recorder's level directly (pill.level_source), not through here.
        if self.recorder and self.window.is_visible():
            from .pill import level_to_unit
            self.backend.set_mic_level(level_to_unit(self.recorder.level))

    def _close_recorder(self) -> None:
        if self.recorder:
            try:
                self.recorder.close()
            except Exception:
                log.exception("closing microphone")
            self.recorder = None

    # ------------------------------------------------------------------ settings, tray

    def _on_setting_edited(self, key: str) -> None:
        s = self.settings
        if key == "hotkey":
            if self.sm.state in (State.LISTENING, State.STARTING) and not self.locked:
                self._discard("hotkey changed")  # the old keys' release would never be seen
            self.key.set_keys(self._hotkey_groups())
            if self.sm.state == State.IDLE:
                self._update_ready()
        elif key == "preset" and self._model_missing:
            if self._check_model():   # the newly chosen model is on this PC (still LOADING: nothing was loaded)
                self.pill.set_mode("loading", "Loading the speech model")
                self._load_model()
        elif key == "preset" and not self._check_model():
            pass  # the new preset's model isn't on this PC: the welcome / Settings offer its download
        elif key == "preset":
            self._reload_pending = self.sm.state not in (State.IDLE, State.ERROR)
            if not self._reload_pending:
                self.sm.go(State.LOADING)
                self.pill.set_mode("loading", "Switching the speech model")
                self._load_model()
        elif key == "languages" and self._needs_multilingual_model():
            # The processor fallback loaded an English-only model: other languages need another.
            # Paused, loading or mid-dictation: done once Vocet is idle (_apply_pending_reload).
            if self.sm.state == State.IDLE:
                self.sm.go(State.LOADING)
                self.pill.set_mode("loading", "Switching the speech model")
                self._load_model()
        elif key == "languages" and self.transcriber:
            self.worker.submit(self.transcriber.set_languages, list(s["languages"]))  # same thread as transcription
        elif key == "dictionary" and self.transcriber:
            words = [w["term"] for w in s["dictionary"]]
            self.worker.submit(self.transcriber.set_vocabulary, words)  # same thread as transcription
        elif key == "show_idle":
            self.pill.show_idle = s["show_idle"]
            if self.sm.state == State.IDLE:
                self.pill.set_mode("idle")
        elif key == "sounds":
            self.sounds.enabled = s["sounds"]
        elif key == "ai_formatting" and self._ai_started:  # before that, _on_loaded starts it
            self.ai.set_enabled(s["ai_formatting"])
        elif key in ("accent", "theme"):  # "theme": the v2 picker; Backend maps it to its accent
            self._apply_tokens()
            self._refresh_appearance()
        elif key == "start_with_windows":
            settings_mod.set_start_with_windows(s["start_with_windows"])
        elif key == "history_days":
            self.history.prune(s["history_days"])
            self.backend.model.reload()
            self.backend.refresh_stats()

    def _apply_tokens(self) -> None:
        """The chosen accent in Windows' current light/dark, Text size and contrast theme."""
        brand.apply(self.system.mode, self.settings["accent"], self.system.text_scale, palette=self.system.palette)

    def _on_system_appearance(self) -> None:
        """Windows' light/dark, Text size, Animation effects or contrast theme changed: apply it live."""
        self.pill.reduced = self.system.reduced_motion
        self.backend.set_reduced_motion(self.system.reduced_motion)
        self._apply_tokens()
        self._refresh_appearance()

    def _refresh_appearance(self) -> None:
        self.window.refresh_theme()
        self.pill.update()
        self._set_tray(self._tray_state)  # the accent and the taskbar's light/dark both show there

    def _set_tray(self, state: str) -> None:
        """loading | ready | listening | paused, remembered so a new accent can redraw it."""
        self._tray_state = state
        self.tray.setIcon(brand.tray_icon(state, brand.taskbar_is_light()))

    def _ready_tip(self) -> str:
        return f"Vocet: hold {self._hotkey_name()} to dictate"

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.backend.set_mics([d["name"] for d in audio.list_input_devices()])
            self.window.show()

    def _build_menu(self) -> None:
        """Every window command is also reachable here."""
        menu = QMenu()
        menu.addAction("Open Vocet", self.window.show)
        self.status_action = menu.addAction("Loading the speech model…")
        self.status_action.setEnabled(False)
        menu.addSeparator()
        self.pause_action = menu.addAction("Pause dictation", self.toggle_pause)
        mic_menu = menu.addMenu("Microphone")
        mic_menu.aboutToShow.connect(lambda: self._fill_mic_menu(mic_menu))
        menu.addAction("Settings…", lambda: self.window.show("settings"))
        menu.addSeparator()
        menu.addAction("Quit Vocet", self.quit)
        self.menu = menu  # keep a reference
        self.tray.setContextMenu(menu)

    def _fill_mic_menu(self, menu: QMenu) -> None:
        """Rebuilt every time it opens, so newly plugged-in mics show up."""
        menu.clear()
        group = QActionGroup(menu)
        names = [d["name"] for d in audio.list_input_devices()]
        self.backend.set_mics(names)
        for name in [None] + names:
            action = QAction(name or "Windows default", menu, checkable=True)
            action.setChecked(name == self.settings["mic"])
            action.triggered.connect(lambda _=False, n=name: self.backend.setSetting("mic", n or ""))
            group.addAction(action)
            menu.addAction(action)

    def _on_resume_requested(self) -> None:
        """backend.resume() (QML): only acts while actually paused, so a stray call can't pause us."""
        if self.sm.state == State.PAUSED:
            self.toggle_pause()

    def toggle_pause(self) -> None:
        if self.sm.state == State.IDLE:
            self.sm.go(State.PAUSED)
            self.pause_action.setText("Resume dictation")
            self.pill.set_mode("hidden")
            self._set_tray("paused")
            self.tray.setToolTip("Vocet: paused")
            self.backend.set_status("Paused")
        elif self.sm.state == State.PAUSED:
            self.sm.go(State.IDLE)
            self.pause_action.setText("Pause dictation")
            self.pill.set_mode("idle")
            self._update_ready()
            self._apply_pending_reload()

    def quit(self) -> None:
        """Never waits long: a model load can sit in a driver for minutes, and
        a frozen quit also blocks a newer copy that is taking over. Loads are abandoned (their
        threads are daemons) and this process's loading-marker entries are removed, so a quit is
        never mistaken for a crash."""
        from . import hardware
        log.info("quitting; network attempts blocked this session: %d", len(self.guard.blocked))
        hardware.stop_loading()           # first: the worker stops waiting for a load, no new one starts
        self.key.uninstall()
        self._abandon_mic_opening()
        self._close_recorder()
        self.backend.mic_test.stop()
        if self.downloader:
            self.downloader.cancel()
        self.ai.close()
        self.worker.shutdown(wait=False, cancel_futures=True)
        self.worker_idle = _join_worker(self.worker, QUIT_WAIT_S)
        if self.worker_idle and self.transcriber:   # never close it under a dictation still running
            self.transcriber.close()
        elif not self.worker_idle:
            log.warning("the worker was still busy after %.0f s; exiting without waiting for it", QUIT_WAIT_S)
        self.window.close()
        self.tray.hide()
        self.history.close()
        self.qt.exit(0)  # exit(), not quit(): quit() would ask the hidden window to close first

    def _abandon_mic_opening(self) -> None:
        """Quit while the mic is still opening: whatever it opens is closed (here, or by its thread
        if it's still inside the driver), and quitting waits at most MIC_OPEN_WAIT_S for it."""
        job, self._mic_job = self._mic_job, None
        if job is None:
            return
        with job.lock:
            job.abandoned = True
        rec = job.take()
        if rec is not None:
            _close_quietly(rec)
        if job.thread is not None and job.thread is not threading.current_thread():
            job.thread.join(MIC_OPEN_WAIT_S)
            if job.thread.is_alive():
                log.warning("the microphone was still opening after %.0f s; quitting anyway", MIC_OPEN_WAIT_S)


QUIT_WAIT_S = 3.0   # at most this long for the worker to finish its job (a paste, a transcription)


def _join_worker(worker: ThreadPoolExecutor, timeout: float) -> bool:
    """Waits up to timeout for the executor's thread to end (after shutdown). True if it did."""
    deadline = time.monotonic() + timeout
    for t in list(getattr(worker, "_threads", ())):
        t.join(max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            return False
    return True


_VERSION_RE = re.compile(r"[0-9A-Za-z._-]{1,40}")  # code_version() is 12 hex; tests use e.g. "new-bbb"


def parse_hello(message: bytes) -> str | None:
    """The version in a "hello <version>" handshake, or None if the message isn't exactly that.
    Nothing else is accepted, and the version is safe to log (no newlines to forge log lines)."""
    try:
        text = message.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    if not text.startswith("hello "):
        return None
    version = text[len("hello "):]
    return version if _VERSION_RE.fullmatch(version) else None


def is_vocet_process(pid: int) -> bool:
    """Whether pid is Vocet itself (Python running vocet.pyw or -m vocet), run by the same
    Windows account as this copy. Any other process can at most make this copy show its window."""
    try:
        proc, me = psutil.Process(pid), psutil.Process()
        if proc.username() != me.username():
            return False
        cmd = proc.cmdline()
    except (psutil.Error, OSError):
        return False
    if not cmd or Path(cmd[0]).name.lower() not in ("python.exe", "pythonw.exe"):
        return False
    args = [a.lower() for a in cmd[1:]]
    return any(Path(a).name == "vocet.pyw" for a in args) or any(
        a == "-m" and nxt == "vocet" for a, nxt in zip(args, args[1:]))


def _pipe_client_is_vocet(sock) -> bool:
    """Asks Windows which process is on the other end of the pipe (Qt's descriptor is the pipe handle)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetNamedPipeClientProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    kernel32.GetNamedPipeClientProcessId.restype = wintypes.BOOL
    pid = wintypes.ULONG()
    try:
        ok = kernel32.GetNamedPipeClientProcessId(int(sock.socketDescriptor()), ctypes.byref(pid))
    except (OSError, TypeError, ValueError, ctypes.ArgumentError):
        return False
    return bool(ok and pid.value) and is_vocet_process(pid.value)


def _pipe_server_pid(sock) -> int:
    """The process id of the server on the other end of a connected client socket, or 0."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetNamedPipeServerProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    kernel32.GetNamedPipeServerProcessId.restype = wintypes.BOOL
    pid = wintypes.ULONG()
    try:
        ok = kernel32.GetNamedPipeServerProcessId(int(sock.socketDescriptor()), ctypes.byref(pid))
    except (OSError, TypeError, ValueError, ctypes.ArgumentError):
        return 0
    return pid.value if ok else 0


HANDOVER_WAIT_S = 600.0   # how long a new copy waits for an older one that said "restarting" to exit


def _wait_for_exit(pid: int, timeout: float) -> bool:
    """Waits until process pid has ended. True if it did within timeout."""
    try:
        psutil.Process(pid).wait(timeout)
    except psutil.NoSuchProcess:
        return True
    except psutil.TimeoutExpired:
        return False
    except psutil.Error:
        return not psutil.pid_exists(pid)
    return True


def _hand_over(name: str | None = None, wait_s: float | None = None) -> bool:
    """Talk to a Vocet that's already running on pipe `name`. True if it keeps running (so we exit).

    It answers "ok" (same code: it opens its window) or "restarting" (it's older code: it quits).
    After "restarting" we wait for that process to end, however long its quit takes (up to
    HANDOVER_WAIT_S), and only then start: a fixed wait could give up while the old copy was still
    finishing, and then neither copy would be left running. The server's
    process id comes from Windows, and it must be a Vocet process before its answer counts.
    """
    name = name or INSTANCE_NAME
    wait_s = HANDOVER_WAIT_S if wait_s is None else wait_s
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(300):
        return False
    server_pid = _pipe_server_pid(sock)
    if server_pid and not is_vocet_process(server_pid):
        log.warning("a process that isn't Vocet holds the single-instance pipe; ignoring it")
        sock.abort()
        return False
    sock.write(f"hello {VERSION}".encode())
    sock.flush()
    reply = bytes(sock.readAll()).decode(errors="replace").strip() if sock.waitForReadyRead(1500) else ""
    sock.disconnectFromServer()
    if reply != "restarting":
        return True
    if server_pid:
        if not _wait_for_exit(server_pid, wait_s):
            log.warning("the older Vocet didn't quit within %.0f s; trying to start anyway", wait_s)
        return False
    deadline = time.time() + 8     # no process id (shouldn't happen): wait until its pipe is gone
    while time.time() < deadline:
        probe = QLocalSocket()
        probe.connectToServer(name)
        if not probe.waitForConnected(200):
            return False
        probe.disconnectFromServer()
        time.sleep(0.2)
    log.warning("the older Vocet didn't quit in time; starting anyway")
    return False


def _find_running_copy() -> bool:
    """True if a Vocet that keeps running answered on the per-user pipe."""
    return _hand_over(INSTANCE_NAME)


MUTEX_NAME = "Local\\" + INSTANCE_NAME
ERROR_ALREADY_EXISTS, WAIT_ABANDONED = 183, 0x80
_instance_mutex = None  # held for the whole process; Windows releases it when the process ends


def _mutex(name: str, timeout_ms: int):
    """(handle, owned): creates or opens the named mutex and waits up to timeout_ms to own it."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle = kernel32.CreateMutexW(None, True, name)
    if not handle:
        return None, True  # no mutex at all (shouldn't happen): don't refuse to start over it
    if ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
        return handle, True  # created it, so we own it
    return handle, kernel32.WaitForSingleObject(handle, timeout_ms) in (0, WAIT_ABANDONED)


def _claim_instance(timeout_ms: int) -> bool:
    """Become the only running copy by owning a named mutex, waiting up to timeout_ms for an
    older copy to exit. Windows gives a mutex to exactly one process. The handshake alone had a
    race: two launches in the same second (a double-click) both started, and every dictation was
    pasted twice."""
    global _instance_mutex
    _instance_mutex, owned = _mutex(MUTEX_NAME, timeout_ms)
    return owned


def main() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    setup_logging()
    guard = privacy.lock_down()
    qt = QApplication(sys.argv)
    qt.setApplicationName("Vocet")
    qt.setQuitOnLastWindowClosed(False)
    if _find_running_copy():
        log.info("already running; asked it to open its window")
        return
    if not _claim_instance(10_000):
        # Another copy launched at the same moment won the lock and runs now: open its window instead.
        if _hand_over():
            log.info("already running (started a moment ago); asked it to open its window")
        else:
            log.warning("another copy holds the single-instance lock but doesn't answer; not starting a second one")
        return
    log.info("starting version %s (network guard active%s, terminal window: %s)", VERSION,
             ", TEST MODE" if TEST_WAV else "", "yes" if ctypes.windll.kernel32.GetConsoleWindow() else "none")
    app = VocetApp(qt, guard)
    app.start()
    code = qt.exec()
    if not getattr(app, "worker_idle", True):
        # A job is still running on the worker (quit() waited QUIT_WAIT_S for it). Python would
        # wait for it at exit and freeze the quit it just finished, so end the process now.
        log.info("process exiting (worker still busy)")
        logging.shutdown()
        os._exit(code)
    sys.exit(code)
