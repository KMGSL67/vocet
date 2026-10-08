"""Puts text at the cursor of whatever app has focus: clipboard + Ctrl+V.

Why not type the text key by key (SendInput with KEYEVENTF_UNICODE)? It's slow
for long text, some apps drop or reorder the characters, and typing a newline
presses Enter, which *sends* a Discord or Teams message. Pasting is one atomic
action that almost every app supports.

Rules this module guarantees:
1. The user's clipboard is saved first and restored afterwards (every format we
   can safely copy: text, rich text, HTML, images as DIB, file lists...).
2. Our temporary clipboard entry is marked so Windows clipboard history (Win+V)
   and Cloud Clipboard sync ignore it. Dictated text must not leave the machine.
3. If the user copies something new while we wait, we don't restore over it.
4. Dictated text is only ever pasted, never executed: no Enter key is ever sent,
   and newlines are flattened, except for AI-formatted text going into an app on
   LINE_BREAK_APPS, where a pasted line break is plainly text.
   Terminals, browsers and everything else always get one line.
5. Nothing is pasted into a password field (UI Automation IsPassword), and nothing
   is pasted if the window in front changed since you pressed the hotkey. Both
   raise before Ctrl+V, and the clipboard is restored either way.
"""

import ctypes
import logging
import queue
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from ctypes import wintypes

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# Clipboard formats whose data is a GDI handle or owner-drawn, not an HGLOBAL
# memory block. They can't be copied as bytes. Windows re-creates CF_BITMAP etc.
# from CF_DIB, which we do keep.
_UNCOPYABLE = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}  # BITMAP METAFILEPICT PALETTE ENHMETAFILE OWNERDISPLAY DSP*

for fn, args, res in [
    ("OpenClipboard", [wintypes.HWND], wintypes.BOOL),
    ("CloseClipboard", [], wintypes.BOOL),
    ("EmptyClipboard", [], wintypes.BOOL),
    ("EnumClipboardFormats", [wintypes.UINT], wintypes.UINT),
    ("GetClipboardData", [wintypes.UINT], wintypes.HANDLE),
    ("SetClipboardData", [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
    ("RegisterClipboardFormatW", [wintypes.LPCWSTR], wintypes.UINT),
    ("GetClipboardSequenceNumber", [], wintypes.DWORD),
    ("GetForegroundWindow", [], wintypes.HWND),
    ("GetAsyncKeyState", [ctypes.c_int], ctypes.c_short),
]:
    getattr(user32, fn).argtypes, getattr(user32, fn).restype = args, res
for fn, args, res in [
    # restype matters: without it ctypes assumes a 32-bit int and cuts 64-bit handles in half
    ("GetModuleHandleW", [wintypes.LPCWSTR], wintypes.HMODULE),
    ("GlobalAlloc", [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL),
    ("GlobalLock", [wintypes.HGLOBAL], ctypes.c_void_p),
    ("GlobalUnlock", [wintypes.HGLOBAL], wintypes.BOOL),
    ("GlobalSize", [wintypes.HGLOBAL], ctypes.c_size_t),
    ("GlobalFree", [wintypes.HGLOBAL], wintypes.HGLOBAL),
]:
    getattr(kernel32, fn).argtypes, getattr(kernel32, fn).restype = args, res

_NO_HISTORY_FORMATS = [  # documented by Microsoft for clipboard managers / history / cloud sync
    ("ExcludeClipboardContentFromMonitorProcessing", b"\x00"),
    ("CanIncludeInClipboardHistory", b"\x00\x00\x00\x00"),
    ("CanUploadToCloudClipboard", b"\x00\x00\x00\x00"),
]


class ClipboardBusy(RuntimeError):
    pass


class FocusChanged(RuntimeError):
    """The window in front isn't the one you were dictating into, so nothing was pasted."""


class PasswordField(RuntimeError):
    """The focused field is a password field, so nothing was pasted."""


# Apps where a pasted line break is text, never a command or "send": an
# allowlist by program file name. Not browsers (a web page can be a terminal), not editors with a
# built-in terminal, never a terminal.
LINE_BREAK_APPS = {"winword.exe", "outlook.exe", "olk.exe", "onenote.exe", "notepad.exe", "wordpad.exe",
                   "notion.exe", "obsidian.exe", "ms-teams.exe", "teams.exe", "slack.exe"}


def keeps_line_breaks(app_path: str) -> bool:
    return app_path.replace("/", "\\").rsplit("\\", 1)[-1].lower() in LINE_BREAK_APPS


def clean_for_insertion(text: str, keep_lines: bool = False) -> str:
    """What actually gets pasted. Flattens newlines/tabs so a paste can never act
    like pressing Enter (e.g. run a command in a terminal or send a chat message).
    keep_lines (AI-formatted text into a LINE_BREAK_APPS app): line breaks stay, as \\r\\n,
    with at most one empty line in a row and none at the start or end."""
    if keep_lines:
        kept: list[str] = []
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = " ".join(line.split())
            if line or (kept and kept[-1]):
                kept.append(line)
        text = "\r\n".join(kept).strip()
    else:
        text = " ".join(text.split())  # collapses \n, \r, \t and runs of spaces
    if not text:
        return ""
    # A trailing space so the next dictation doesn't glue on, except after Chinese: it's written
    # without spaces, so the next dictation simply continues.
    from .textproc import ends_without_space
    return text if ends_without_space(text) else f"{text} "


class _Clipboard:
    """Context manager: open the clipboard, retrying because other apps hold it briefly.

    pump: called between retries. While our promise is on the clipboard, the app holding it
    may be waiting for *us* to render the text (WM_RENDERFORMAT), so we must answer.
    """

    def __init__(self, pump=None):
        self.pump = pump

    def __enter__(self):
        for _ in range(20):
            if user32.OpenClipboard(None):
                return self
            if self.pump:
                self.pump()
            time.sleep(0.01)
        raise ClipboardBusy("clipboard is locked by another application")

    def __exit__(self, *exc):
        user32.CloseClipboard()


def _hglobal_from_bytes(data: bytes) -> wintypes.HGLOBAL:
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    return handle


def _set(fmt: int, data: bytes) -> None:
    handle = _hglobal_from_bytes(data)
    if not user32.SetClipboardData(fmt, handle):
        kernel32.GlobalFree(handle)  # ownership only passes to Windows on success


def save_clipboard() -> list[tuple[int, bytes]]:
    saved = []
    with _Clipboard():
        fmt = user32.EnumClipboardFormats(0)
        while fmt:
            if fmt not in _UNCOPYABLE and not 0x200 <= fmt <= 0x3FF:  # private/GDI-object ranges
                handle = user32.GetClipboardData(fmt)
                if handle:
                    size = kernel32.GlobalSize(handle)
                    ptr = kernel32.GlobalLock(handle)
                    if ptr:
                        saved.append((fmt, ctypes.string_at(ptr, size)))
                        kernel32.GlobalUnlock(handle)
            fmt = user32.EnumClipboardFormats(fmt)
    return saved


def _mark_private() -> None:
    for name, data in _NO_HISTORY_FORMATS:
        _set(user32.RegisterClipboardFormatW(name), data)


def restore_clipboard(saved: list[tuple[int, bytes]], pump=None) -> None:
    with _Clipboard(pump):
        user32.EmptyClipboard()
        for fmt, data in saved:
            _set(fmt, data)
        _mark_private()  # don't create a duplicate entry in Win+V history


def set_clipboard_text(text: str) -> int:
    """Puts text on the clipboard (hidden from history/cloud). Returns the sequence number."""
    with _Clipboard():
        user32.EmptyClipboard()
        _set(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
        _mark_private()
    return user32.GetClipboardSequenceNumber()


def get_clipboard_text() -> str | None:
    with _Clipboard():
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)


# --- simulated Ctrl+V -----------------------------------------------------------------

VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, VK_V = 0x10, 0x11, 0x12, 0x5B, 0x5C, 0x56
KEY_GAP_S = 0.008


def _wait_for_modifiers_released(timeout_s: float = 1.5) -> None:
    """If Shift/Alt/Win are still physically held, Ctrl+V would become e.g. Win+Ctrl+V
    (with the Ctrl + Win hotkey, people sometimes let go of Win a moment after Ctrl)."""
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (VK_SHIFT, VK_MENU, VK_LWIN, VK_RWIN)):
            return
        time.sleep(0.01)


def send_paste(target_hwnd: int | None = None) -> None:
    """Ctrl down, V down, V up, Ctrl up, with 8 ms between them.

    Sent as one burst (all four in a single SendInput), modern XAML apps such as
    Windows 11 Notepad dropped about 15% of pastes (4-5 of 30 in a stress test,
    2026-09-28). With 8 ms gaps: 0 of 60 dropped. Costs 24 ms. Each event is
    marked as Vocet's own, so the hotkey hook ignores it (hotkey.VOCET_MARK).

    target_hwnd: the window you were dictating into. Checked again *after* the
    wait for modifiers (up to 1.5 s), right before the first key, so a window
    switch during that wait can't send the text elsewhere (raises FocusChanged).
    """
    from .hotkey import send_key
    _wait_for_modifiers_released()
    if target_hwnd is not None and foreground_window() != target_hwnd:
        raise FocusChanged("the window in front changed before Ctrl+V")
    for n, (vk, up) in enumerate(((VK_CONTROL, False), (VK_V, False), (VK_V, True), (VK_CONTROL, True))):
        if n:
            time.sleep(KEY_GAP_S)
        if not send_key(vk, up):
            raise OSError(f"SendInput failed ({ctypes.get_last_error()}): blocked by an admin window?")


# --- delayed rendering: know *when* the target app reads the text ------------------------
#
# A fixed "wait 350 ms, then restore the clipboard" is a guess. A busy app can read
# the clipboard later than that, and then the paste is silently lost (seen in the
# Notepad end-to-end test, 2026-09-28). Instead, Vocet puts only a *promise* of the
# text on the clipboard (SetClipboardData with no data = delayed rendering). When
# an app actually reads it, Windows sends our hidden window WM_RENDERFORMAT, we
# hand over the text, and only then restore your clipboard.

WM_RENDERFORMAT, WM_RENDERALLFORMATS, WM_DESTROYCLIPBOARD = 0x0305, 0x0306, 0x0307
HWND_MESSAGE = wintypes.HWND(-3)
PM_REMOVE = 0x0001
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


for fn, args, res in [
    ("DefWindowProcW", [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], LRESULT),
    ("RegisterClassW", [ctypes.POINTER(_WNDCLASSW)], wintypes.ATOM),
    ("CreateWindowExW", [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                         wintypes.HINSTANCE, wintypes.LPVOID], wintypes.HWND),
    ("PeekMessageW", [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT], wintypes.BOOL),
    ("TranslateMessage", [ctypes.POINTER(wintypes.MSG)], wintypes.BOOL),
    ("DispatchMessageW", [ctypes.POINTER(wintypes.MSG)], LRESULT),
    ("GetOpenClipboardWindow", [], wintypes.HWND),
    ("GetClipboardOwner", [], wintypes.HWND),
    ("GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
]:
    getattr(user32, fn).argtypes, getattr(user32, fn).restype = args, res


def _pid_of(hwnd) -> int:
    pid = wintypes.DWORD()
    if hwnd:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


_by_hwnd: dict = {}  # hidden window -> its _ClipboardPromise


def _dispatch(hwnd, msg, wparam, lparam):
    """One window procedure for the class, routing to the right instance."""
    owner = _by_hwnd.get(hwnd)
    if owner is not None:
        return owner.handle(hwnd, msg, wparam, lparam)
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_WNDPROC = WNDPROC(_dispatch)  # module-level, so it can never be garbage-collected
_CLASS_NAME = "VocetClipboardPromise"
_class_atom = None


class _ClipboardPromise:
    """A hidden message-only window that owns the clipboard while one paste is in flight.

    Created and pumped on one thread: Vocet's single worker thread.
    """

    def __init__(self):
        global _class_atom
        if _class_atom is None:
            wc = _WNDCLASSW(lpfnWndProc=_WNDPROC, hInstance=kernel32.GetModuleHandleW(None),
                            lpszClassName=_CLASS_NAME)
            _class_atom = user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, _CLASS_NAME, "", 0, 0, 0, 0, 0,
                                           HWND_MESSAGE, None, kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise OSError(f"CreateWindowExW failed: {ctypes.get_last_error()}")
        _by_hwnd[self.hwnd] = self
        self.text = ""
        self.read_by: list[int] = []   # process ids of apps that read the text

    def handle(self, hwnd, msg, wparam, lparam):
        if msg == WM_RENDERFORMAT and wparam == CF_UNICODETEXT:
            if self.text is None:
                return 0  # the paste was called off (see withdraw): whoever asks now gets nothing
            # Someone is reading. We're inside *their* OpenClipboard, so only set the data.
            self.read_by.append(_pid_of(user32.GetOpenClipboardWindow()))
            handle = _hglobal_from_bytes((self.text + "\0").encode("utf-16-le"))
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
            return 0
        if msg in (WM_RENDERALLFORMATS, WM_DESTROYCLIPBOARD):
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def offer(self, text: str) -> None:
        """Puts the promise on the clipboard, hidden from clipboard history and cloud sync."""
        self.text, self.read_by = text, []
        for _ in range(20):
            if user32.OpenClipboard(self.hwnd):
                break
            time.sleep(0.01)
        else:
            raise ClipboardBusy("clipboard is locked by another application")
        try:
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_UNICODETEXT, None)  # no data = "ask me when you need it"
            _mark_private()
        finally:
            user32.CloseClipboard()

    def still_owner(self) -> bool:
        """Anyone who copies something takes ownership of the clipboard."""
        return user32.GetClipboardOwner() == self.hwnd

    def withdraw(self) -> None:
        """The paste was called off before Ctrl+V: never hand the text to anyone from now on."""
        self.text = None

    def pump(self) -> None:
        """Answers pending messages (a WM_RENDERFORMAT from an app that has the clipboard open)."""
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def wait_for_read(self, target_pid: int, timeout_s: float) -> float | None:
        """Pumps messages until an app has read the text.

        Returns how long to wait before restoring (a short grace so the app can
        finish reading), or None if nobody read it within timeout_s.
        - Read by the target app (or anonymously, pid 0): 50 ms grace.
        - Read by another process: classic consoles paste through conhost.exe, and a
          clipboard manager might peek. The text stays rendered, so give the target
          250 ms more to read it too before restoring.
        """
        msg = wintypes.MSG()
        deadline = time.perf_counter() + timeout_s
        while time.perf_counter() < deadline:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if self.read_by:
                return 0.05 if any(pid in (target_pid, 0) for pid in self.read_by) else 0.25
            if not self.still_owner():
                return 0.0  # the user copied something else meanwhile; nothing left to wait for
            time.sleep(0.004)
        return None


_promises: dict[int, _ClipboardPromise] = {}  # one hidden window per thread


# --- password fields: ask UI Automation whether the focused element is one --------------
#
# Plain ctypes COM (no comtypes dependency). Vtable slots from UIAutomationClient.h,
# checked 2026-09-29 against a Win32 EDIT with and without ES_PASSWORD:
#   IUIAutomation:        6 ElementFromHandle, 8 GetFocusedElement
#   IUIAutomation2:       61 put_ConnectionTimeout, 63 put_TransactionTimeout
#   IUIAutomationElement: 35 get_CurrentIsPassword
# The COM object lives on one daemon thread (COM objects belong to the thread that
# made them), and callers wait at most PASSWORD_CHECK_TIMEOUT_S. If UI Automation is
# missing, slow or stuck, the answer is None and Vocet pastes as it always did.

PASSWORD_CHECK_TIMEOUT_S = 0.3
_CLSID_CUIAUTOMATION8 = "{e22ad333-b25f-460c-83d0-0581107395c9}"
_CLSID_CUIAUTOMATION = "{ff48dba4-60ef-4201-aa87-54103eef594e}"
_IID_IUIAUTOMATION = "{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}"
_IID_IUIAUTOMATION2 = "{34723aff-0c9d-49d0-9896-7ab52df8cd8a}"
_VT_QUERYINTERFACE, _VT_RELEASE = 0, 2
_VT_ELEMENT_FROM_HANDLE, _VT_GET_FOCUSED_ELEMENT = 6, 8
_VT_PUT_CONNECTION_TIMEOUT, _VT_PUT_TRANSACTION_TIMEOUT = 61, 63
_VT_GET_CURRENT_IS_PASSWORD = 35


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> _GUID:
    g = _GUID()
    if ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(g)):
        raise OSError("bad GUID")
    return g


def _vcall(obj, index: int, argtypes: list, *args) -> int:
    """Calls a COM method by its vtable slot. Returns the HRESULT (negative = failed)."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    method = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[index])
    return method(obj, *args)


def _release(obj) -> None:
    if obj:
        _vcall(obj, _VT_RELEASE, [])


class _Uia:
    """The IUIAutomation object. Only ever touched on _PasswordProbe's thread."""

    def __init__(self):
        ole32 = ctypes.WinDLL("ole32")
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole32.CoInitializeEx.restype = ctypes.c_long
        ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD,
                                           ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
        ole32.CoCreateInstance.restype = ctypes.c_long
        ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED: no message pump needed on this thread
        self.ptr = ctypes.c_void_p()
        for clsid in (_CLSID_CUIAUTOMATION8, _CLSID_CUIAUTOMATION):  # 8 = Windows 8+, has timeouts
            if ole32.CoCreateInstance(ctypes.byref(_guid(clsid)), None, 1,  # CLSCTX_INPROC_SERVER
                                      ctypes.byref(_guid(_IID_IUIAUTOMATION)), ctypes.byref(self.ptr)) >= 0:
                break
        else:
            raise OSError("UI Automation is not available")
        v2 = ctypes.c_void_p()
        if _vcall(self.ptr, _VT_QUERYINTERFACE, [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)],
                  ctypes.byref(_guid(_IID_IUIAUTOMATION2)), ctypes.byref(v2)) >= 0 and v2:
            # Defaults are 2 s / 20 s: a hung app would keep this thread stuck that long.
            _vcall(v2, _VT_PUT_CONNECTION_TIMEOUT, [wintypes.DWORD], 500)
            _vcall(v2, _VT_PUT_TRANSACTION_TIMEOUT, [wintypes.DWORD], 500)
            _release(v2)

    def is_password(self, hwnd: int | None = None) -> bool | None:
        """The focused element (or the element for hwnd, used by the self-test)."""
        element = ctypes.c_void_p()
        if hwnd is None:
            hr = _vcall(self.ptr, _VT_GET_FOCUSED_ELEMENT, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(element))
        else:
            hr = _vcall(self.ptr, _VT_ELEMENT_FROM_HANDLE, [wintypes.HWND, ctypes.POINTER(ctypes.c_void_p)],
                        hwnd, ctypes.byref(element))
        if hr < 0 or not element:
            return None
        try:
            flag = wintypes.BOOL()
            if _vcall(element, _VT_GET_CURRENT_IS_PASSWORD, [ctypes.POINTER(wintypes.BOOL)], ctypes.byref(flag)) < 0:
                return None
            return bool(flag.value)
        finally:
            _release(element)


class _PasswordProbe:
    """One daemon thread that owns the UIA object and answers one question at a time.

    Daemon, so a check stuck inside a frozen app can never keep Vocet from exiting.
    """

    def __init__(self):
        self._jobs: queue.Queue = queue.Queue()
        self._pending: Future | None = None
        threading.Thread(target=self._run, name="uia-password-check", daemon=True).start()

    def _run(self) -> None:
        try:
            uia = _Uia()
        except Exception as exc:
            uia, error = None, exc
        while True:
            future, hwnd = self._jobs.get()
            if uia is None:
                future.set_exception(error)
                continue
            try:
                future.set_result(uia.is_password(hwnd))
            except Exception as exc:
                future.set_exception(exc)

    def ask(self, hwnd: int | None, timeout_s: float) -> bool | None:
        if self._pending is not None and not self._pending.done():
            return None  # the previous check is still stuck in an unresponsive app
        self._pending = future = Future()
        self._jobs.put((future, hwnd))
        try:
            return future.result(timeout_s)
        except FutureTimeout:
            log.info("password-field check took longer than %.0f ms; pasting as usual", timeout_s * 1000)
        except Exception as exc:
            log.info("password-field check unavailable (%s); pasting as usual", type(exc).__name__)
        return None


_probe: _PasswordProbe | None = None
_probe_lock = threading.Lock()


def prepare_password_check() -> None:
    """Starts the UI Automation thread early, so the first dictation doesn't pay for it."""
    global _probe
    with _probe_lock:
        if _probe is None:
            _probe = _PasswordProbe()


def focused_is_password(timeout_s: float = PASSWORD_CHECK_TIMEOUT_S, hwnd: int | None = None) -> bool | None:
    """True if the focused field is a password field, False if not, None if UI Automation
    can't tell in time (then the caller pastes as usual). Never raises."""
    try:
        prepare_password_check()
        return _probe.ask(hwnd, timeout_s)
    except Exception as exc:
        log.info("password-field check failed (%s); pasting as usual", type(exc).__name__)
        return None


def _restore_if_ours(promise: "_ClipboardPromise", saved: list) -> bool:
    """Puts the user's clipboard back unless they copied something new meanwhile."""
    if not promise.still_owner():
        log.info("clipboard changed during paste; not restoring over the user's new copy")
        return False
    restore_clipboard(saved, pump=promise.pump)
    return True


def insert_text(text: str, target_hwnd: int | None = None, timeout_s: float = 2.0, on_pasted=None,
                keep_lines: bool = False) -> dict:
    """Pastes text into the focused app, then restores the clipboard once the app has read it.

    target_hwnd: the window you were dictating into. If another window is in front
        right before Ctrl+V, raises FocusChanged and pastes nothing.
    on_pasted: called right after Ctrl+V is sent, so the UI can confirm immediately.
    Raises PasswordField (before touching the clipboard) if the focused field is a
    password field. The user's clipboard is always restored, also when nothing was
    read and when something fails half-way; the only exception is when the user
    copied something new meanwhile (then their new copy is kept).
    keep_lines: keep line breaks (only for AI-formatted text into a LINE_BREAK_APPS app).
    Returns timings, and read_confirmed: whether an app actually read the text.
    """
    text = clean_for_insertion(text, keep_lines)
    if not text:
        return {"inserted": False}
    t0 = time.perf_counter()
    _wait_for_modifiers_released()  # first, so the checks below see where focus really ends up
    if focused_is_password():
        raise PasswordField("the focused field is a password field")
    if target_hwnd is not None and foreground_window() != target_hwnd:
        raise FocusChanged("the window in front changed before pasting")  # before the clipboard is touched
    tid = threading.get_ident()
    promise = _promises.get(tid)
    if promise is None:
        promise = _promises[tid] = _ClipboardPromise()
    target_pid = _pid_of(target_hwnd or foreground_window())
    saved = save_clipboard()
    keys_sent = False
    try:
        promise.offer(text)
        send_paste(target_hwnd)  # checks the window once more, right before the first key
        keys_sent = True
        pasted_at = time.perf_counter()
        if on_pasted:
            on_pasted()
        grace = promise.wait_for_read(target_pid, timeout_s)
        read_at = time.perf_counter()
        confirmed = grace is not None
        if confirmed:
            time.sleep(grace)  # let the app finish reading any other formats it asked for
        else:
            log.warning("no app read the pasted text within %.1f s", timeout_s)
    except BaseException:
        if not keys_sent:
            promise.withdraw()  # called off before Ctrl+V: nobody gets the text now
        try:
            _restore_if_ours(promise, saved)  # a window switch, a failed SendInput...: never leave our text behind
        except Exception as exc:  # noqa: BLE001 - e.g. ClipboardBusy: the original reason must win
            # Otherwise "you switched windows" (text kept in History) became "couldn't reach the
            # clipboard", and the dictation was lost.
            log.warning("couldn't restore the clipboard after a paste that didn't happen (%s)", type(exc).__name__)
        raise
    restored = _restore_if_ours(promise, saved)
    return {"inserted": True, "paste_ms": (pasted_at - t0) * 1000, "pasted_at": pasted_at,
            "read_ms": (read_at - pasted_at) * 1000, "read_confirmed": confirmed,
            "restored": restored, "saved_formats": len(saved)}


def foreground_window() -> int:
    return user32.GetForegroundWindow() or 0
