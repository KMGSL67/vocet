"""Global push-to-talk hotkey (a single key or a combination like Ctrl + Win),
using a Windows low-level keyboard hook.

Why a hook and not RegisterHotKey? RegisterHotKey only reports key *down*.
Push-to-talk needs to know when the keys are *released*.

A hotkey is a list of groups, and every group needs one key held:
    Ctrl + Win  = [(LCtrl, RCtrl), (LWin, RWin)]
    Right Ctrl  = [(RCtrl,)]

Rules:
- The hook callback must return fast. If it takes too long (LowLevelHooksTimeout,
  about 300-1000 ms), Windows passes the key on without us, and after repeated
  timeouts silently removes the hook. So the hook runs on its own thread, which does
  nothing but wait for keys (a busy Qt thread can't delay it, and the whole desktop's
  keyboard doesn't wait for Vocet's UI), and the callback only updates a few fields
  and queues the work to the Qt thread.
- A missed key-up must never keep the microphone on.
  While a push-to-talk recording runs, watch_release() checks the keys' real state
  (GetAsyncKeyState) every 50 ms and treats "not held" (twice in a row) as the
  release. The timer runs only while recording, so idle Vocet uses no CPU for it.
- Keys are passed on to Windows, except Space and Esc while dictating (below).
- Hotkey + another key (Ctrl+Win+D = new virtual desktop, RCtrl+C = copy) is a
  shortcut, not dictation, so the recording is cancelled and the shortcut works.
- Hotkey + Space switches to hands-free. That Space is swallowed.
- Esc while dictating cancels. That Esc is swallowed too.
- Win pressed and released alone opens the Start menu. When a combination with
  Win becomes active, Vocet sends an unassigned "mask" key, so Windows knows Win
  was part of a combination (the same trick AutoHotkey uses).
- Keystrokes Vocet sends itself (the Ctrl+V paste, the mask key) carry a marker
  in dwExtraInfo and are ignored.

Known limit: a normal (non-admin) app doesn't receive keys while an
administrator window has focus. Windows forbids that (UIPI).
"""

import ctypes
import logging
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

log = logging.getLogger("vocet")

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
LLKHF_INJECTED = 0x10
VK_SPACE, VK_ESCAPE = 0x20, 0x1B
VK_LCONTROL, VK_RCONTROL, VK_LWIN, VK_RWIN = 0xA2, 0xA3, 0x5B, 0x5C
MASK_VK = 0xE8          # unassigned virtual-key code
VOCET_MARK = 0xEC40      # dwExtraInfo on every keystroke Vocet sends
RELEASE_POLL_MS = 50    # how often a push-to-talk recording checks that the keys are still held
WM_QUIT = 0x0012

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def _physically_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class PushToTalkKey(QObject):
    """pressed() when the hotkey becomes held, released() when it's let go,
    cancelled() if another key joins in, hands_free() for Space while held,
    escape() for Esc while `listening` is set. Signals are always emitted on the Qt thread."""

    pressed = Signal()
    released = Signal()
    cancelled = Signal()
    hands_free = Signal()
    escape = Signal()
    _to_qt = Signal(object)  # the hook thread's hand-over to the Qt thread

    def __init__(self, groups, test_mode: bool = False):
        super().__init__()
        self.listening = False            # set by the app while it records
        # Test mode: react only to synthetic key presses (the end-to-end test drives Vocet
        # with SendInput) and ignore the physical keyboard, so a test instance can never
        # respond to you typing. Normal mode is the opposite. Vocet's own keys: always ignored.
        self.test_mode = test_mode
        self._is_down = _physically_down  # replaced in unit tests
        self._proc = HOOKPROC(self._callback)  # keep a reference or it gets garbage-collected
        self._hook = None
        self._thread = None
        self._thread_id = 0
        self._lock = threading.Lock()     # the hook thread and the Qt thread share the key state
        self._to_qt.connect(self._run_on_qt, Qt.QueuedConnection)
        self._release_poll = QTimer(self, interval=RELEASE_POLL_MS)
        self._release_poll.timeout.connect(self._check_release)
        self._seen_up = 0
        self.missed_releases = 0          # releases only the key-state check noticed
        self.set_keys(groups)

    def set_keys(self, groups) -> None:
        with self._lock:
            self.groups = [tuple(g) for g in groups]
            self._combo = {vk for g in self.groups for vk in g}
            self._uses_win = bool(self._combo & {VK_LWIN, VK_RWIN})
            self._held: set[int] = set()
            self._active = self._chorded = False
        self.stop_watching()

    # ------------------------------------------------------------------ the hook thread

    def install(self) -> None:
        ready = threading.Event()
        failure = []

        def run():
            self._thread_id = kernel32.GetCurrentThreadId()
            hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
            if not hook:
                failure.append(ctypes.get_last_error())
                ready.set()
                return
            self._hook = hook
            ready.set()
            msg = wintypes.MSG()
            # The hook callback runs inside GetMessageW. Nothing is ever posted here but WM_QUIT.
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
            user32.UnhookWindowsHookEx(hook)

        self._thread = threading.Thread(target=run, name="vocet-hotkey-hook", daemon=True)
        self._thread.start()
        ready.wait(5)
        if not self._hook:
            raise OSError(f"SetWindowsHookExW failed: {failure[0] if failure else 'timed out'}")

    def uninstall(self) -> None:
        self.stop_watching()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            thread.join(2)
        self._hook = None

    def _callback(self, code: int, wparam: int, lparam: int) -> int:
        # Keep this minimal: the key waits for it (and so does every other app on the PC).
        if code == 0:  # HC_ACTION
            kb = KBDLLHOOKSTRUCT.from_address(lparam)
            if (kb.dwExtraInfo != VOCET_MARK and kb.vkCode != MASK_VK
                    and bool(kb.flags & LLKHF_INJECTED) == self.test_mode):
                with self._lock:
                    swallow = self._on_key(kb.vkCode, wparam in (WM_KEYDOWN, WM_SYSKEYDOWN), kb.scanCode)
                if swallow:
                    return 1  # swallowed (Space for hands-free, Esc to cancel)
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _post(self, fn) -> None:
        """Runs fn on the Qt thread, soon (callable from any thread)."""
        self._to_qt.emit(fn)

    @Slot(object)
    def _run_on_qt(self, fn) -> None:
        fn()

    # ------------------------------------------------------------------ the key state (pure logic)

    def _satisfied(self) -> bool:
        return all(any(vk in self._held for vk in g) for g in self.groups)

    def _on_key(self, vk: int, is_down: bool, scan: int = 0) -> bool:
        """Pure state logic, kept separate from the hook so it can be unit-tested.
        Returns True if this key event should be swallowed."""
        if self.listening and vk == VK_ESCAPE:
            if is_down:
                self._post(self.escape.emit)
            return True
        if is_down:
            # Drop keys whose "up" we missed (e.g. released on the lock screen).
            self._held = {k for k in self._held if self._is_down(k)}
            self._held.add(vk)
        else:
            self._held.discard(vk)

        if not self._active:
            others_down = self._held - self._combo
            if is_down and vk in self._combo and self._satisfied() and not others_down:
                self._active, self._chorded = True, False
                if self._uses_win:
                    self._post(send_mask_key)
                self._post(self.pressed.emit)
            return False

        if is_down and vk not in self._combo:
            if vk == VK_SPACE and not self._chorded:
                self._post(self.hands_free.emit)
                return True
            if not self._chorded:
                self._chorded = True  # e.g. Ctrl+Win+D: a shortcut, not dictation
                self._post(self.cancelled.emit)
            return False
        if not is_down and vk in self._combo and not self._satisfied():
            self._active = False
            if not self._chorded:
                self._post(self.released.emit)
        return False

    # ------------------------------------------------------------------ the safety net for a missed key-up

    def watch_release(self) -> None:
        """While a push-to-talk recording runs, also checks the keys' real state, so a key-up the
        hook never saw still ends it. stop_watching() when it ends or goes hands-free."""
        self._seen_up = 0
        self._release_poll.start()

    def stop_watching(self) -> None:
        self._release_poll.stop()

    @property
    def watching(self) -> bool:
        return self._release_poll.isActive()

    def _keys_held_now(self) -> bool:
        return all(any(self._is_down(vk) for vk in g) for g in self.groups)

    def _check_release(self) -> None:
        if not self._release_poll.isActive():  # stopped (hands-free, ended) after this tick was queued
            return
        with self._lock:
            if not self._active:        # the hook saw the release (or the chord) itself
                self._release_poll.stop()
                return
            if self._keys_held_now():
                self._seen_up = 0
                return
            self._seen_up += 1
            if self._seen_up < 2:       # twice in a row, so the hook's own key-up always comes first
                return
            self._active = False
            self._held = {k for k in self._held if self._is_down(k)}
            chorded = self._chorded
        self._release_poll.stop()
        self.missed_releases += 1
        log.warning("hotkey: the keyboard hook missed the key release; the key-state check ended it")
        if self._thread is not None:
            # Windows removes a hook that timed out too often, without telling us: install it again.
            self.uninstall()
            try:
                self.install()
            except OSError:
                log.exception("hotkey: couldn't install the keyboard hook again")
        if not chorded:
            self.released.emit()


# --- sending keys (shared with insertion.py) ----------------------------------------

INPUT_KEYBOARD, KEYEVENTF_KEYUP = 1, 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):  # only here so the union has the right size
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", _MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def send_key(vk: int, up: bool = False) -> bool:
    """One key event, marked as Vocet's own so the hotkey hook ignores it."""
    event = (INPUT * 1)(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(
        wVk=vk, dwFlags=KEYEVENTF_KEYUP if up else 0, dwExtraInfo=VOCET_MARK)))
    return user32.SendInput(1, event, ctypes.sizeof(INPUT)) == 1


def send_mask_key() -> None:
    """Tells Windows the held Win key is part of a combination, so releasing it
    doesn't open the Start menu."""
    send_key(MASK_VK)
    send_key(MASK_VK, up=True)
