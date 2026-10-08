"""Keeps Vocet offline and telemetry-free.

Three layers, cheapest first:
1. Environment flags that make Hugging Face libraries never touch the network.
2. An explicit opt-out for the dependency that ships telemetry: OpenVINO's
   `import openvino` sends a Google Analytics event unless an opt-out file exists.
3. A socket guard that blocks (and records) any connection that is not to
   this machine. It only sees Python-level sockets, not connections made by
   native code.
"""

import contextlib
import logging
import os
import re
import socket
import threading
import traceback
from pathlib import Path


def set_offline_env() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def disable_openvino_telemetry() -> None:
    """Writes Intel's documented opt-out file. Must run before `import openvino`."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return
    consent = Path(base) / "Intel Corporation" / "openvino_telemetry"
    if not consent.exists() or consent.read_text().strip() != "0":
        consent.parent.mkdir(parents=True, exist_ok=True)
        consent.write_text("0\n")


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class NetworkGuard:
    """Replaces socket.connect so only loopback connections are allowed.

    Blocked attempts are recorded in `self.blocked`, so the log can report how many connections
    were refused instead of just claiming there were none.

    One exception, only while it runs: `allowing(hosts)` around the speech-model download you
    start yourself (model_download.py): any thread may reach those hosts until the block ends.
    connect() only sees an IP address, so the names are matched when they're resolved: addresses
    that an allowed name resolved to may be connected to while the block runs. Nothing else is
    let through.
    """

    def __init__(self):
        self.blocked: list[str] = []
        self.allowed: list[str] = []          # connections let through by the exception, for the log
        self._original = None
        self._suffixes: tuple[str, ...] = ()
        self._allowed_ips: set[str] = set()
        self._resolver_users = 0
        self._original_getaddrinfo = None
        self._lock = threading.RLock()

    def permits(self, host: str) -> bool:
        """Whether a connection to this address is allowed now."""
        with self._lock:
            return host in _LOOPBACK or host in self._allowed_ips

    @staticmethod
    def _matches(name, suffixes) -> str | None:
        if not isinstance(name, str) or not suffixes:
            return None
        name = name.lower().rstrip(".")
        return next((s for s in suffixes if name == s or name.endswith("." + s)), None)

    def _host_allowed(self, name) -> bool:
        return self._matches(name, self._suffixes) is not None

    def _record(self, host, infos) -> None:
        ips = {info[4][0] for info in infos}
        with self._lock:
            if self._host_allowed(host):
                self._allowed_ips.update(ips)

    def _use_resolver(self) -> None:
        """Wraps socket.getaddrinfo while the exception is active (so the names can be matched)."""
        with self._lock:
            self._resolver_users += 1
            if self._resolver_users > 1:
                return
            original = self._original_getaddrinfo = socket.getaddrinfo
            guard = self

            def recording_getaddrinfo(host, *args, **kwargs):
                infos = original(host, *args, **kwargs)
                guard._record(host, infos)
                return infos

            socket.getaddrinfo = recording_getaddrinfo

    def _release_resolver(self) -> None:
        with self._lock:
            self._resolver_users -= 1
            if self._resolver_users == 0 and self._original_getaddrinfo is not None:
                socket.getaddrinfo, self._original_getaddrinfo = self._original_getaddrinfo, None

    @contextlib.contextmanager
    def allowing(self, host_suffixes: tuple[str, ...]):
        """Lets connections to these hosts (and their subdomains) through while the block runs."""
        with self._lock:
            self._suffixes = tuple(s.lower() for s in host_suffixes)
        self._use_resolver()
        try:
            yield self
        finally:
            self._release_resolver()
            with self._lock:
                self._suffixes, self._allowed_ips = (), set()

    def install(self) -> "NetworkGuard":
        self._original = socket.socket.connect
        guard = self

        def guarded_connect(sock, address):
            host = address[0] if isinstance(address, tuple) else str(address)
            if not guard.permits(host):
                guard.blocked.append(f"{host}:{address[1]}" if isinstance(address, tuple) else host)
                raise ConnectionRefusedError(f"Vocet network guard blocked a connection to {host}")
            if host not in _LOOPBACK:
                guard.allowed.append(host)
            return guard._original(sock, address)

        socket.socket.connect = guarded_connect
        return self

    def uninstall(self) -> None:
        if self._original is not None:
            socket.socket.connect = self._original
            self._original = None


def lock_down() -> NetworkGuard:
    """Everything Vocet calls first, before any model or network library is used."""
    set_offline_env()
    disable_openvino_telemetry()
    return NetworkGuard().install()


# --- log redaction ----------------------------------------------------------------------
#
# Logs are local, but people paste them into bug reports. So:
# - the user profile path (it contains the Windows user name) becomes %USERPROFILE%, and
#   the bare user name becomes <user>, in messages and tracebacks alike;
# - values put into a message can't contain control characters, so a string from another
#   process can't forge extra log lines;
# - records marked extra={NO_EXC_MESSAGE: True} log the traceback (where it happened) but not
#   the exception's message, which could quote dictated text or clipboard contents.
# Code must still never log dictated text, clipboard contents or window titles itself.

NO_EXC_MESSAGE = "vocet_no_exc_message"
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _short_path(path: str) -> str:
    """The 8.3 short form of a path (a profile folder shown as JOHNSM~1) that some tools print; the path
    itself if there is none."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(520)
        n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
        return buf.value if 0 < n < len(buf) else path
    except (AttributeError, OSError):
        return path


def _redaction_patterns(profile: str | None = None, user: str | None = None) -> list[tuple[re.Pattern, str]]:
    profile = profile if profile is not None else os.environ.get("USERPROFILE") or str(Path.home())
    user = user if user is not None else os.environ.get("USERNAME") or Path(profile).name
    patterns = []
    variants = set()
    for p in {profile.rstrip("\\/"), _short_path(profile).rstrip("\\/")}:
        if len(p) > 3:  # never redact a bare drive
            variants |= {p, p.replace("\\", "/"), p.replace("\\", "\\\\")}  # as-is, posix, repr()
    if variants:
        alternation = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
        patterns.append((re.compile(alternation, re.IGNORECASE), "%USERPROFILE%"))
    if user and len(user) >= 3:
        patterns.append((re.compile(rf"(?<![\w-]){re.escape(user)}(?![\w-])", re.IGNORECASE), "<user>"))
    return patterns


_PATTERNS: list | None = None


def redact(text: str, patterns: list | None = None) -> str:
    """Replaces the user profile path with %USERPROFILE% and the user name with <user>."""
    global _PATTERNS
    if patterns is None:
        if _PATTERNS is None:
            _PATTERNS = _redaction_patterns()
        patterns = _PATTERNS
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


def one_line(value: str) -> str:
    r"""Control characters (newlines too) shown as \xNN, so a value can't start a fake log line."""
    return _CONTROL.sub(lambda m: f"\\x{ord(m.group()):02x}", value)


def _traceback_without_message(exc_info) -> str:
    etype, value, tb = exc_info
    frames = "".join(traceback.format_tb(tb))
    return f"Traceback (most recent call last):\n{frames}{etype.__name__}: (message not logged)"


class RedactingFormatter(logging.Formatter):
    """The formatter for Vocet's log file. See the comment block above."""

    def format(self, record: logging.LogRecord) -> str:
        record = logging.makeLogRecord(record.__dict__)  # a copy: never change what other handlers see
        if isinstance(record.args, tuple):
            record.args = tuple(a if isinstance(a, (int, float)) else one_line(str(a)) for a in record.args)
        if record.exc_info and getattr(record, NO_EXC_MESSAGE, False):
            record.exc_text = _traceback_without_message(record.exc_info)
        return redact(super().format(record))


def tidy_crash_log(path: Path, keep_bytes: int = 256_000) -> None:
    """faulthandler writes straight to crash.log, past any formatter. At the next start, redact
    it the same way and keep only its last keep_bytes (it was never rotated)."""
    try:
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        tidy = redact(text)
        if len(tidy.encode("utf-8")) > keep_bytes:
            tidy = tidy.encode("utf-8")[-keep_bytes:].decode("utf-8", errors="ignore")
        if tidy != text:
            path.write_text(tidy, encoding="utf-8")
    except OSError:
        pass
