"""The speech-model download you start yourself (first run on another PC).

Vocet ships without its speech model (large-v3-turbo is about 0.8 GB). On a PC that doesn't
have it, the welcome (and Settings › Speech model) offers a Download button. Nothing downloads
by itself. What a download does, and nothing more:

- Only the commit pinned in models_manifest.json, and only the files the manifest lists (the
  same guarantee as `allow_patterns` in engines.download: never an upstream .py file).
- Into a staging folder next to the model (`<model>.download`), so a half-finished download is
  never mistaken for a model: `engines.is_downloaded` only sees the real folder.
- Then `integrity.verify`: every file's size and SHA-256 against the manifest. A mismatch
  deletes the bad file and says so; nothing is loaded.
- Only then are the files moved into place.
- Files already complete in the staging folder (a cancelled or interrupted download) are
  kept, so trying again only fetches what's missing; verify still hashes every file.
- The network guard (privacy.NetworkGuard) lets connections through only to Hugging Face's
  hosts, and only while the download runs. No Hugging Face token is sent (token=False), and
  hf_xet (native code the guard can't see) is switched off for the download.

`run()` takes a `fetch` function, so tests use a fake one: no network in tests.
"""

import contextlib
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from . import integrity

log = logging.getLogger(__name__)

HF_HOSTS = ("huggingface.co", "hf.co")   # the Hub, its LFS/CDN hosts (cdn-lfs.hf.co, ...)
SOURCE = "Hugging Face"

# Sentences the UI shows (plain, no jargon; the SHA-256 detail goes to the log).
MSG_VERIFY_FAILED = "The file was damaged during the download, so Vocet deleted it. Try again."
MSG_NETWORK = "Couldn’t reach Hugging Face. Check your internet connection and try again."
MSG_DISK = "There isn’t enough free space for the speech model. Free some up and try again."
MSG_FAILED = "The download didn’t finish. Check your connection and try again."


class DownloadCancelled(Exception):
    pass


@dataclass(frozen=True)
class Plan:
    key: str                     # "openvino/large-v3-turbo"
    repo: str
    revision: str
    files: dict                  # name -> size in bytes
    target: Path                 # the model's folder

    @property
    def total(self) -> int:
        return sum(self.files.values())

    @property
    def staging(self) -> Path:
        return self.target.with_name(self.target.name + ".download")


def size_label(n: int) -> str:
    """"0.8 GB" from 750 MB up (one decimal), else "245 MB" (decimal units)."""
    return f"{n / 1e9:.1f} GB" if n >= 750e6 else f"{max(1, round(n / 1e6))} MB"


def plan(engine: str, model: str, models_dir: Path | None = None) -> Plan:
    """What downloading this model means: the pinned commit, the files and their sizes.
    Raises ModelIntegrityError if the manifest doesn't pin and hash it (then it can't be verified)."""
    key = f"{engine}/{model}"
    e = integrity.entry(key)
    rev = integrity.revision(key)
    if e is None or rev is None or not e.get("files"):
        raise integrity.ModelIntegrityError(f"{key}: not pinned and hashed in the manifest, so it can't be downloaded")
    names = [n for n in e["files"] if integrity.allowed_file(n)]
    if len(names) != len(e["files"]):
        raise integrity.ModelIntegrityError(f"{key}: the manifest lists a file type Vocet never downloads")
    folder = (models_dir or integrity.MODELS_DIR) / engine / model
    return Plan(key, e["repo"], rev, {n: int(e["files"][n]["size"]) for n in sorted(names)}, folder)


# A fetch function downloads one file: fetch(repo, revision, name, folder, on_bytes, cancelled).
# It writes folder/name, calls on_bytes(n) as data arrives, and raises DownloadCancelled soon
# after cancelled() turns true.
Fetch = Callable[[str, str, str, Path, Callable[[int], None], Callable[[], bool]], None]


def run(p: Plan, fetch: Fetch | None = None, on_progress: Callable[[int, int], None] | None = None,
        cancel: threading.Event | None = None, on_verifying: Callable[[], None] | None = None,
        hash_cache: Path | None = None) -> Path:
    """Downloads, verifies and installs a model. Returns its folder.
    Raises DownloadCancelled, integrity.ModelIntegrityError (checksum) or the fetch's own error."""
    fetch = fetch or hf_fetch
    cancel = cancel or threading.Event()
    report = on_progress or (lambda done, total: None)
    staging = p.staging
    staging.mkdir(parents=True, exist_ok=True)
    total = p.total

    def have(name: str) -> bool:
        try:
            return (staging / name).stat().st_size == p.files[name]
        except OSError:
            return False

    done = sum(size for name, size in p.files.items() if have(name))
    report(done, total)
    t0 = time.perf_counter()
    for name, size in p.files.items():
        if cancel.is_set():
            raise DownloadCancelled()
        if have(name):
            continue
        before = done
        got = [0]

        def on_bytes(n: int, before=before, size=size) -> None:
            got[0] += n
            report(before + min(got[0], size), total)

        fetch(p.repo, p.revision, name, staging, on_bytes, cancel.is_set)
        if cancel.is_set():
            raise DownloadCancelled()
        if not have(name):
            raise OSError(f"{p.key}: {name} arrived with the wrong size")
        done = before + size
        report(done, total)
    log.info("downloaded %s (%d files, %.0f MB) in %.1f s", p.key, len(p.files), total / 1e6, time.perf_counter() - t0)

    if on_verifying:
        on_verifying()
    try:
        integrity.verify(p.key, staging, cache_file=hash_cache)
    except integrity.ModelIntegrityError:
        # Which file failed is in the exception (and the log); delete every file that doesn't
        # match, so trying again fetches them fresh.
        for name in p.files:
            path = staging / name
            try:
                if path.exists() and integrity.sha256_file(path) != integrity.entry(p.key)["files"][name]["sha256"]:
                    path.unlink()
            except OSError:
                pass
        raise
    _install(p)
    return p.target


def _install(p: Plan) -> None:
    """Moves the verified files into the model's folder, then removes the staging folder."""
    p.target.mkdir(parents=True, exist_ok=True)
    for name in p.files:
        dest = p.target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(p.staging / name, dest)
    shutil.rmtree(p.staging, ignore_errors=True)


def hf_fetch(repo: str, revision: str, name: str, folder: Path, on_bytes: Callable[[int], None],
             cancelled: Callable[[], bool]) -> None:
    """One file from the Hugging Face Hub at a pinned commit (the real network; never in tests)."""
    import huggingface_hub.constants as hf_constants
    from huggingface_hub import hf_hub_download
    from tqdm.auto import tqdm as base_tqdm

    class Progress(base_tqdm):  # huggingface_hub reports bytes through a tqdm bar: ours shows nothing
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            if cancelled():
                raise DownloadCancelled()
            if n:
                on_bytes(int(n))

    # privacy.set_offline_env() put the Hub in offline mode for the whole process; lift it for
    # this call only. And no hf_xet: its native code would bypass the network guard.
    saved = hf_constants.HF_HUB_OFFLINE, hf_constants.HF_HUB_DISABLE_XET
    hf_constants.HF_HUB_OFFLINE, hf_constants.HF_HUB_DISABLE_XET = False, True
    try:
        hf_hub_download(repo, name, revision=revision, local_dir=folder, token=False, tqdm_class=Progress)
    finally:
        hf_constants.HF_HUB_OFFLINE, hf_constants.HF_HUB_DISABLE_XET = saved


def error_message(exc: BaseException) -> str:
    """One sentence for the UI."""
    if isinstance(exc, integrity.ModelIntegrityError):
        return MSG_VERIFY_FAILED
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:   # ENOSPC
        return MSG_DISK
    name = type(exc).__name__
    if isinstance(exc, (ConnectionError, TimeoutError)) or "Connect" in name or "Timeout" in name or "Offline" in name:
        return MSG_NETWORK
    return MSG_FAILED


# --------------------------------------------------------------------------- the Qt side


class Downloader(QObject):
    """Runs one download on its own thread and reports on the Qt thread.

    state: needed | downloading | verifying | ready | failed | cancelled.
    `changed` carries the whole state dict (what Backend.speechModel shows). Progress is sent at
    most every 100 ms or 0.5 %, so a fast connection can't flood the UI thread."""

    changed = Signal(dict)
    finished = Signal(bool)          # True: the model is installed and verified

    def __init__(self, p: Plan, guard=None, fetch: Fetch | None = None, hash_cache: Path | None = None):
        super().__init__()
        self.plan = p
        self.guard = guard
        self.fetch = fetch
        self.hash_cache = hash_cache
        self.cancel_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._last_sent = (0.0, -1.0)
        self.state = self._state("needed")

    def _state(self, state: str, done: int = 0, message: str = "") -> dict:
        total = self.plan.total
        return {"state": state, "done": done, "total": total, "progress": (done / total) if total else 0.0,
                "size": size_label(total), "doneLabel": size_label(done) if done else "0 MB",
                "source": SOURCE, "message": message}

    def _emit(self, state: dict) -> None:
        self.state = state
        self.changed.emit(dict(state))

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self) -> bool:
        if self.running:
            return False
        self.cancel_event.clear()
        self._emit(self._state("downloading"))
        self.thread = threading.Thread(target=self._run, name="model-download", daemon=True)
        self.thread.start()
        return True

    def cancel(self) -> None:
        self.cancel_event.set()

    def _progress(self, done: int, total: int) -> None:
        now, frac = time.monotonic(), done / total if total else 0.0
        last_t, last_frac = self._last_sent
        if done >= total or now - last_t >= 0.1 or frac - last_frac >= 0.005:
            self._last_sent = (now, frac)
            self._emit(self._state("downloading", done))

    def _run(self) -> None:
        allow = self.guard.allowing(HF_HOSTS) if self.guard is not None else contextlib.nullcontext()
        try:
            with allow:
                run(self.plan, fetch=self.fetch, on_progress=self._progress, cancel=self.cancel_event,
                    on_verifying=lambda: self._emit(self._state("verifying", self.plan.total)),
                    hash_cache=self.hash_cache)
        except DownloadCancelled:
            log.info("model download cancelled")
            self._emit(self._state("cancelled", 0))
            self.finished.emit(False)
        except Exception as exc:  # noqa: BLE001 - every failure becomes one sentence
            log.error("model download failed: %s: %s", type(exc).__name__, exc)
            self._emit(self._state("failed", 0, error_message(exc)))
            self.finished.emit(False)
        else:
            self._emit(self._state("ready", self.plan.total))
            self.finished.emit(True)
