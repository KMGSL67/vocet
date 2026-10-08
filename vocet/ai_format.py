"""AI formatting in the dictation path: when it's on and ready, every dictation
goes through formatter.Formatter before it's pasted, with a hard time limit.

- **Never slower than a limit:** `format()` waits at most `deadline_s(text)` for the whole call
  (queueing, reading the prompt, writing the answer, the guard). Past it, the original text is
  pasted and the model is told to stop at its next token. Finishing in the background would only
  hold the graphics chip for text nobody uses, so it's cancelled, not kept.
- **Never loses a dictation:** a model error, a guard rejection, a timeout, a language it doesn't
  cover (LANGUAGES: not Chinese or Hindi) or "not ready yet" all return the original text.
- **Never on the hotkey thread:** `format()` runs on the dictation worker; the model itself runs on
  this module's own thread. Loading and unloading happen there too, in the background.
- **One chip, one job:** Whisper and the formatter share the graphics chip. Run together, both get
  slower (measured), so transcription and every model call take `gpu_lock` in turn.
- **Turns itself off where it can't work**: the model isn't downloaded, less than
  16 GB of memory (VOCET_RAM_GB overrides), no Intel graphics chip, or the chip is too slow (the
  warm-up gives < 15 tokens/s or > 400 ms to the first token). Three timeouts in a row pause it
  until the next start or until you switch it off and on again.
- **Crash-safe loading:** the load runs through hardware's marker file as device "llm-gpu", so a
  driver crash while loading marks it bad for 7 days instead of crashing every start. The check for
  an Intel graphics chip goes through the same marker, with its own time limit, and asks only the
  GPU plugin (never the NPU's), so a driver that crashes or hangs when asked can't crash-loop the
  app either. Quitting while it loads isn't a crash: the app removes its
  marker entries then (hardware.stop_loading).
- **Switching off while it loads**: Settings says "off" at once, and the load
  is abandoned: this module's thread stops waiting for it (and skips the warm-ups), and the model
  is closed the moment the load ends, unless it was switched on again meanwhile, in which case
  that load is used instead of starting a second one. A late "ready" from an abandoned load never
  reaches Settings while the switch is off.

Only one sentence per state reaches the user (Settings, under the switch). Nothing here logs
dictated text: only categories and timings.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Callable

from . import formatter

log = logging.getLogger(__name__)

MODEL = "phi-4-mini"
MODEL_SIZE = "2.3 GB"
LLM_DEVICE = "llm-gpu"          # its key in hardware's marker file and bad-device list
GPU_CHECK_DEVICE = "llm-gpu-list"   # asking the GPU driver which chips it has: its own key, so a
                                    # check that works never clears a strike against the load itself
# Where it runs: English and German (the guard's word lists and the prompt), and French
# and Spanish, which passed the checker on FLEURS + the dictation items (0 unsafe outputs
# accepted). Not Chinese (the guard can't compare it yet) or Hindi (beta).
LANGUAGES = ("en", "de", "fr", "es")

MIN_RAM_GB = 16                 # total memory
MIN_FREE_GB = 5                 # free when it would load: it adds about 2.9 GB
MIN_TOKENS_PER_S = 15
MAX_TTFT_MS = 400
LOAD_TIMEOUT_S = 120.0          # first compile included, like the speech model on the GPU
GPU_CHECK_TIMEOUT_S = 20.0      # asking the GPU plugin for its chips' names
SLOW_IN_A_ROW = 3               # timeouts in a row before it pauses itself

# The time limit for the whole call: 1.2 s up to 20 words, then 15 ms per word, at most 3 s.
# Measured on the eval set: 1.2 s covers the p95 of short dictations with the GPU idle.
BASE_DEADLINE_S, BASE_WORDS, PER_WORD_S, MAX_DEADLINE_S = 1.2, 20, 0.015, 3.0

OFF, LOADING, READY, UNAVAILABLE = "off", "loading", "ready", "unavailable"

MSG_LOADING = "Getting AI formatting ready…"
MSG_ON = "On. Tries to fix spelling, lists and self-corrections on your PC."
MSG_NOT_DOWNLOADED = (f"The AI formatting model ({MODEL_SIZE}) isn’t on this PC yet: "
                      "run download-ai-model.cmd in Vocet’s folder to add it.")
MSG_MEMORY = f"This PC needs at least {MIN_RAM_GB} GB of memory for AI formatting."
MSG_FREE_MEMORY = "There isn’t enough free memory for AI formatting right now; close some apps and try again."
MSG_GPU = "This PC’s graphics chip isn’t supported for AI formatting; dictation works the same without it."
MSG_STOPPED = "AI formatting stopped while it was loading, so Vocet waits a few days before trying it again."
MSG_SLOW = "This PC’s graphics chip is too slow for AI formatting; dictation works the same without it."
MSG_DAMAGED = "The AI formatting model’s files are damaged or were changed, so Vocet won’t use them."
MSG_FAILED = "AI formatting couldn’t start; everything else still works."
MSG_PAUSED = "AI formatting was too slow several times in a row, so Vocet paused it until the next start."


def deadline_s(text: str) -> float:
    words = len(text.split())
    return min(MAX_DEADLINE_S, BASE_DEADLINE_S + PER_WORD_S * max(0, words - BASE_WORDS))


# --------------------------------------------------------------------------- the machine

@dataclass
class Machine:
    downloaded: bool
    ram_gb: float
    intel_gpu: bool
    llm_crashed: bool = False    # "llm-gpu" is marked bad: loading it crashed or stopped recently


def _ram_gb() -> float:
    env = os.environ.get("VOCET_RAM_GB", "")
    try:
        if env:
            return float(env)
    except ValueError:
        pass
    import psutil
    return psutil.virtual_memory().total / 2**30


def free_gb() -> float:
    import psutil
    return psutil.virtual_memory().available / 2**30


_gpu_names: list[str] | None = None   # this process's answer (the chips don't change while it runs)
_gpu_names_lock = threading.Lock()


def _list_gpus() -> list[str]:
    """The names of the graphics chips OpenVINO's GPU plugin sees. Only that plugin is loaded:
    `Core().available_devices` would load every plugin, the NPU's included."""
    from . import privacy
    privacy.disable_openvino_telemetry()
    import openvino
    core = openvino.Core()
    try:
        ids = [str(i) for i in core.get_property("GPU", "AVAILABLE_DEVICES")]
    except Exception:  # noqa: BLE001 - an older plugin without the property: the default chip
        ids = []
    devices = [f"GPU.{i}" for i in ids] or ["GPU"]
    return [str(core.get_property(d, "FULL_DEVICE_NAME")) for d in devices]


def _intel_gpu() -> bool:
    """An Intel graphics chip that OpenVINO sees and that hasn't crashed a load recently.

    Asking the driver runs like a load (hardware._attempt, device GPU_CHECK_DEVICE): a crash
    marker, a time limit, its own daemon thread. A driver that crashes when asked is then skipped
    for 7 days, and one that hangs costs GPU_CHECK_TIMEOUT_S once per process, not every job."""
    global _gpu_names
    from . import hardware
    allowed = hardware.allowed_devices()
    if allowed is not None and "gpu" not in allowed:
        return False
    hardware.check_previous_start()          # a check (or load) that crashed last time counts now
    bad = hardware.bad_devices()
    if "gpu" in bad or LLM_DEVICE in bad or GPU_CHECK_DEVICE in bad:
        return False
    with _gpu_names_lock:
        if _gpu_names is None:
            try:
                attempt = hardware.Attempt("openvino", "gpu-names", GPU_CHECK_DEVICE)
                _gpu_names = hardware._attempt(attempt, lambda _a: _list_gpus(), GPU_CHECK_TIMEOUT_S, None)
            except hardware.LoadCancelled:
                return False                     # quitting: ask again next time
            except Exception as exc:  # noqa: BLE001 - no plugin, no driver, stuck: not supported
                log.warning("couldn't list the graphics chips for AI formatting (%s)", type(exc).__name__)
                _gpu_names = []
        names = _gpu_names
    return any("intel" in n.lower() for n in names)


def machine() -> Machine:
    from . import integrity
    from . import hardware
    return Machine(downloaded=integrity.present(f"llm/{MODEL}", formatter.LLM_DIR / MODEL),
                   ram_gb=_ram_gb(), intel_gpu=_intel_gpu(),
                   llm_crashed=bool({LLM_DEVICE, GPU_CHECK_DEVICE} & set(hardware.bad_devices())))


def reason_unavailable(m: Machine) -> str:
    """The one sentence that says why AI formatting can't run here, or "" if it can try."""
    if not m.downloaded:
        return MSG_NOT_DOWNLOADED
    if m.ram_gb < MIN_RAM_GB - 0.5:     # "16 GB" laptops report a little less than 16 GiB
        return MSG_MEMORY
    if m.llm_crashed:                   # not "unsupported": it's tried again after BAD_FOR_DAYS
        return MSG_STOPPED
    if not m.intel_gpu:
        return MSG_GPU
    return ""


def too_slow(r: formatter.FormatResult) -> bool:
    """The minimum speed (MIN_TOKENS_PER_S, MAX_TTFT_MS), read from a warm-up call."""
    if r.rejected and r.rejected.startswith("model error"):
        return True
    decode_s = (r.ms - r.ttft_ms) / 1000
    tokens_per_s = r.tokens / decode_s if r.tokens > 1 and decode_s > 0 else 0.0
    return tokens_per_s < MIN_TOKENS_PER_S or r.ttft_ms > MAX_TTFT_MS


# --------------------------------------------------------------------------- one dictation

@dataclass
class Outcome:
    text: str          # what to paste: the model's version if it was used, else the original
    status: str        # formatted | unchanged | skipped | off | language | timed out | error | rejected: <why>
    ms: float = 0.0    # time spent here

    @property
    def formatted(self) -> bool:
        return self.status == "formatted"


class _Serial:
    """One background thread running jobs in order, like a one-worker ThreadPoolExecutor, but a
    daemon: quitting never waits for a model stuck in a graphics driver."""

    def __init__(self, name: str):
        self._jobs: queue.SimpleQueue = queue.SimpleQueue()
        self._closed = False
        threading.Thread(target=self._loop, name=name, daemon=True).start()

    def submit(self, fn, *args) -> Future:
        future: Future = Future()
        if self._closed:
            future.set_result(None)
        else:
            self._jobs.put((future, fn, args))
        return future

    def shutdown(self) -> None:
        self._closed = True
        self._jobs.put(None)

    def _loop(self) -> None:
        while (job := self._jobs.get()) is not None:
            future, fn, args = job
            if not future.set_running_or_notify_cancel():
                continue                       # cancelled while it waited
            try:
                future.set_result(fn(*args))
            except BaseException as exc:  # noqa: BLE001 - handed to whoever waits for it
                future.set_exception(exc)


def _make_formatter():
    return formatter.Formatter(formatter.LLM_DIR / MODEL, "GPU", warm_up=False, timeout_s=MAX_DEADLINE_S)


class _Load:
    """One model load, on its own thread, so the formatter's thread can stop waiting for it."""

    def __init__(self):
        self.result = None
        self.error: BaseException | None = None
        self.finished = False           # set under AiFormatting._state_lock
        self.waited = True              # an _apply is waiting for it; False: abandoned
        self.settled = threading.Event()  # finished, and closed if nobody took it


class AiFormatting:
    """Owns the formatter: loads it in the background, formats with a deadline, reports its state.

    on_change(state, message) is called from this module's thread whenever the state changes;
    the app forwards it to the Qt thread. make() builds a formatter (tests pass a fake), probe()
    describes the machine (tests pass a Machine)."""

    def __init__(self, on_change: Callable[[str, str], None] | None = None, *,
                 make: Callable[[], object] | None = None, probe: Callable[[], Machine] | None = None,
                 free: Callable[[], float] | None = None, gpu_lock: threading.Lock | None = None,
                 guarded_load: bool = True):
        self._on_change = on_change or (lambda state, message: None)
        self._make = make or _make_formatter
        self._probe = probe or machine
        self._free = free or free_gb
        self._guarded = guarded_load
        self.gpu_lock = gpu_lock or threading.Lock()
        self._pool = _Serial("ai-format")
        self._state_lock = threading.Lock()
        self.state, self.message = OFF, ""
        self._formatter = None
        self._wanted = False
        self._slow = 0
        self._closed = False
        self._pending: _Load | None = None   # a load still running (maybe abandoned: switched off)

    # ------------------------------------------------------------------ state

    def _set(self, state: str, message: str) -> None:
        with self._state_lock:
            if state in (LOADING, READY) and not self._wanted:
                return        # a late word from a load that was switched off: the switch says off
            if (state, message) == (self.state, self.message):
                return
            self.state, self.message = state, message
        self._announce(state, message)

    def _announce(self, state: str, message: str) -> None:
        log.info("AI formatting: %s", state if state != UNAVAILABLE else f"unavailable ({message})")
        try:
            self._on_change(state, message)
        except Exception:  # noqa: BLE001 - a UI callback must never break formatting
            log.exception("AI formatting state callback")

    @property
    def available(self) -> bool:
        return self.state != UNAVAILABLE

    def check(self) -> None:
        """Looks at the machine in the background, so Settings can say why the switch is off."""
        self._submit(self._check_job)

    def set_enabled(self, on: bool) -> None:
        """The switch changed (or the app started with it on). Loads or unloads in the background.
        Switched off while it loads, Settings says so at once: the load is abandoned in the
        background, and _set ignores the "ready" it might still send."""
        with self._state_lock:
            self._wanted = on
            if self._pending is not None and not self._pending.finished:
                self._pending.waited = on   # on again mid-load: claim it now, so it isn't closed
            stop = not on and self.state in (LOADING, READY)   # nothing waits for the unload
            resume = on and self._pending is not None and self.state == OFF   # off and on mid-load
            if stop:
                self.state, self.message = OFF, ""
            elif resume:
                self.state, self.message = LOADING, MSG_LOADING
        if stop:
            self._announce(OFF, "")
        elif resume:
            self._announce(LOADING, MSG_LOADING)
        if on:
            self._slow = 0            # switching it on again is a fresh try, also after a pause
        self._submit(self._apply)

    def wait_idle(self, timeout: float = 30.0) -> None:
        """Tests: wait until the background work queued so far is done (an abandoned load too)."""
        self._submit(lambda: None).result(timeout)
        pending = self._pending
        if pending is not None:
            pending.settled.wait(timeout)

    def close(self) -> None:
        self._closed = True
        self._pool.shutdown()

    def _submit(self, fn, *args) -> Future:
        return self._pool.submit(fn, *args)

    # ------------------------------------------------------------------ background jobs (own thread)

    def _check_job(self) -> None:
        if self._wanted or self._formatter is not None:
            return                    # _apply decides while it's on
        reason = self._reason()
        self._set(UNAVAILABLE, reason) if reason else self._set(OFF, "")

    def _reason(self) -> str:
        try:
            return reason_unavailable(self._probe())
        except Exception:  # noqa: BLE001
            log.exception("checking whether AI formatting can run")
            return MSG_FAILED

    def _apply(self) -> None:
        if self._closed:
            return
        if not self._wanted:
            self._unload()
            self._drop_claimed_load()
            reason = self._reason()
            self._set(UNAVAILABLE, reason) if reason else self._set(OFF, "")
            return
        if self._formatter is not None:
            self._set(READY, MSG_ON)
            return
        reason = self._reason()
        if not reason and self._free() < MIN_FREE_GB:
            reason = MSG_FREE_MEMORY
        if reason:
            self._set(UNAVAILABLE, reason)
            return
        self._set(LOADING, MSG_LOADING)
        t0 = time.perf_counter()
        load = self._wait_for_load()
        if load is None:
            return                           # switched off (or quitting) while it loaded: abandoned
        if load.error is not None:
            exc = load.error
            from .integrity import ModelIntegrityError
            from .hardware import LoadCancelled
            if self._closed or isinstance(exc, LoadCancelled):
                return                       # quitting: nothing to report
            if not isinstance(exc, Exception):
                raise exc
            if not self._wanted:
                return                       # switched off as it failed: the switch says off
            damaged = isinstance(exc, ModelIntegrityError)
            log.error("AI formatting didn't load: %s", type(exc).__name__ if not damaged else exc)
            self._set(UNAVAILABLE, MSG_DAMAGED if damaged else MSG_FAILED)
            return
        f = load.result
        try:
            for _ in range(2):  # the first compiles and fills the prompt cache, the second is what a
                if not self._wanted or self._closed:   # dictation will see; none once switched off
                    self._close(f)
                    log.info("AI formatting switched off while it loaded; closed it")
                    return
                with self.gpu_lock:
                    probe = f.warm_up()
        except Exception:  # noqa: BLE001
            log.exception("AI formatting warm-up failed")
            self._close(f)
            if self._wanted:
                self._set(UNAVAILABLE, MSG_FAILED)
            return
        log.info("AI formatting loaded in %.1f s; warm-up %.0f ms, first token %.0f ms, %d tokens",
                 time.perf_counter() - t0, probe.ms, probe.ttft_ms, probe.tokens)
        if not self._wanted or self._closed:   # switched off during the last warm-up
            self._close(f)
            return
        if too_slow(probe):
            self._close(f)
            self._set(UNAVAILABLE, MSG_SLOW)
            return
        self._formatter = f                    # switched off from here on: the queued _apply unloads it
        self._set(READY, MSG_ON)

    def _wait_for_load(self) -> _Load | None:
        """Starts the load on its own thread, or waits again for one still running from before (it
        was switched off and on while loading: one load, never two on the chip). Returns the finished
        load, or None once switched off or quitting: the load is then abandoned, and its model is
        closed when it ends (_run_load), unless a later _apply takes it first."""
        with self._state_lock:
            load = self._pending
            if load is None:
                if not self._wanted or self._closed:
                    return None              # switched off before it started: start none
                load = self._pending = _Load()
                threading.Thread(target=self._run_load, args=(load,), name="ai-format-load", daemon=True).start()
            load.waited = True
        while True:
            with self._state_lock:
                if load.finished:
                    if not load.waited:
                        return None          # it ended while switched off: _run_load closed it
                    if self._pending is load:
                        self._pending = None
                    return load              # ours: the caller uses (or closes) its model
                if not self._wanted or self._closed:
                    load.waited = False      # abandoned: _run_load closes it when it ends
                    log.info("AI formatting switched off while it loaded; the load is abandoned")
                    return None
            load.settled.wait(0.05)

    def _drop_claimed_load(self) -> None:
        """Switched off again after switching on had claimed a load that has since ended: nobody
        will take its model now, so close it."""
        with self._state_lock:
            load = self._pending
            if load is None or not load.finished:
                return
            self._pending = None
        if load.result is not None:
            self._close(load.result)
            log.info("AI formatting's abandoned load ended; closed it")

    def _run_load(self, load: _Load) -> None:
        try:
            load.result = self._load()
        except BaseException as exc:  # noqa: BLE001 - handed to whoever waits for it
            load.error = exc
        with self._state_lock:
            load.finished = True
            orphan = not load.waited
            if orphan and self._pending is load:
                self._pending = None
        if orphan and load.result is not None:
            self._close(load.result)
            log.info("AI formatting's abandoned load ended; closed it")
        elif orphan:
            log.info("AI formatting's abandoned load ended with %s", type(load.error).__name__)
        load.settled.set()                    # wakes a waiting _apply at once (or wait_idle)

    def _load(self):
        if not self._guarded:
            return self._make()
        from . import hardware
        hardware.check_previous_start()
        attempt = hardware.Attempt("openvino-genai", MODEL, LLM_DEVICE)
        return hardware._attempt(attempt, lambda _a: self._make(), LOAD_TIMEOUT_S,
                                 hardware.simulated_failures().get(LLM_DEVICE))

    def _unload(self) -> None:
        f, self._formatter = self._formatter, None
        if f is not None:
            self._close(f)
            log.info("AI formatting unloaded")

    @staticmethod
    def _close(f) -> None:
        try:
            f.close()
        except Exception:  # noqa: BLE001
            pass

    def _pause(self) -> None:
        """Too slow several times in a row: stop using it until the next start (or a fresh switch-on)."""
        self._set(UNAVAILABLE, MSG_PAUSED)
        self._submit(self._unload)

    # ------------------------------------------------------------------ one dictation (worker thread)

    def format(self, text: str, language: str, app: str = "") -> Outcome:
        """The text to paste. Blocks the calling (worker) thread for at most deadline_s(text)."""
        t0 = time.perf_counter()
        ms = lambda: (time.perf_counter() - t0) * 1000  # noqa: E731
        f = self._formatter
        if f is None or self.state != READY:
            return Outcome(text, "off")
        if language not in LANGUAGES:
            return Outcome(text, "language")
        reason = formatter.needs_llm(text, language)
        if not reason:
            return Outcome(text, "skipped", ms())    # short and simple: no model, no delay
        limit = deadline_s(text)
        cancel = threading.Event()
        future = self._submit(self._run, f, text, language, app, cancel, reason)
        try:
            r = future.result(timeout=limit)
        except FutureTimeout:
            cancel.set()                  # stops the model at its next token
            future.cancel()               # or before it starts, if it's still queued
            self._slow += 1
            log.info("AI formatting took longer than %.1f s (%d in a row); pasted the original", limit, self._slow)
            if self._slow >= SLOW_IN_A_ROW:
                self._pause()
            return Outcome(text, "timed out", ms())
        except Exception as exc:  # noqa: BLE001
            log.error("AI formatting failed (%s); pasted the original", type(exc).__name__)
            return Outcome(text, "error", ms())
        self._slow = 0
        if r is None:
            return Outcome(text, "off", ms())
        if r.rejected:
            status = "error" if r.rejected.startswith("model error") else f"rejected: {r.rejected}"
            log.info("AI formatting: %s (%.0f ms); pasted the original", status, r.ms)
            return Outcome(text, status, ms())
        if not r.used_llm:
            return Outcome(text, "skipped", ms())
        if r.text == text:
            return Outcome(text, "unchanged", ms())
        return Outcome(r.text, "formatted", ms())

    def _run(self, f, text: str, language: str, app: str, cancel: threading.Event, reason: str = ""):
        if cancel.is_set() or f is not self._formatter:
            return None
        with self.gpu_lock:
            if cancel.is_set():
                return None
            return f.format(text, language, app, cancel=cancel, reason=reason)
