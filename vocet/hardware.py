"""Which chip runs speech, and what Vocet does when one fails.

A preset names a model and the device it's meant for. `plan()` turns it into an ordered list of
attempts: the preset's own device, then the other accelerator (the NPU only for small models,
because compiling a large one there takes minutes), then the processor with a model it runs in
about a second (settings.CPU_TIER). `load()` tries them in that order:

- A Python exception (no such device, out of memory) moves on to the next attempt at once.
- Every attempt runs in its own thread with a timeout, so a load stuck in a driver can't stall
  Vocet for ever. The abandoned load may still finish later: it's closed then, and the kernels it
  compiled stay cached, so the next start is fast.
- A marker file (loading.json in the data folder) is written before each attempt and removed after
  it. If Vocet starts and finds one from an earlier process, that start died while loading. If
  crash.log grew since (faulthandler logged a native crash), the device is marked bad at once; if
  not (Vocet was killed, or Windows shut down mid-load), only after two such starts in a row. A bad
  device is skipped for BAD_FOR_DAYS days or until OpenVINO is updated, so a driver crash can't
  become a crash loop. Only the GPU and the NPU are ever skipped: the processor is the last resort,
  so a bad mark on it is logged and it is tried anyway, always last.
- The processor's timeout is long (LOAD_TIMEOUT_S): nothing comes after it, so giving up early would
  only throw away a slow first load on a small PC.
- Quitting stops waiting for a load (stop_loading) and removes this process's marker entries, so a
  deliberate quit is never counted as a crash.

Test switches. All are off unless set:
    VOCET_DEVICES=cpu             only these devices exist (comma list of gpu, npu, cpu)
    VOCET_CPU_CORES=4             pretend the PC has 4 cores: the thread count and CPU affinity follow
    VOCET_PROBE_FAIL=gpu:raise    make a device fail: raise | hang | crash (a real access violation)
    VOCET_LOAD_TIMEOUT_S=5        one load timeout for every device
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .integrity import ModelIntegrityError

log = logging.getLogger(__name__)

ACCELERATORS = ("gpu", "npu")                          # tried in this order after the preset's own device
NPU_MODELS = {"base.en", "small.en", "base", "small"}   # large models take minutes to compile on the NPU
LARGE_MODELS = {"large-v3-turbo", "distil-large-v3"}    # several seconds per dictation on a processor
# First compile included (est.; NPU small.en: to verify). The processor is the last resort, so its
# limit only catches a load that is really stuck: a 2-core PC hashing, compiling and warming up the
# large model the first time can take minutes.
LOAD_TIMEOUT_S = {"gpu": 120.0, "npu": 180.0, "cpu": 900.0}
BAD_FOR_DAYS = 7

# One plain sentence each: no chip names, no jargon.
MSG_CPU = "Running on the processor, so dictation may take a second or two."
MSG_CPU_SLOW = "Running on the processor, so dictation may take a few seconds."
MSG_OTHER_CHIP = "Vocet switched to another chip in this PC."
MSG_FAILED = "Couldn’t load the speech model. Restart Vocet to try again."


# --------------------------------------------------------------------------- where things live

def _app_dir() -> Path:
    from . import settings   # read at call time: VOCET_HOME and tests move it
    return settings.APP_DIR


def cache_dir() -> Path:
    """OpenVINO's compiled-kernel cache: per user and writable (never the install folder)."""
    return _app_dir() / "openvino-cache"


def _state_file() -> Path:
    return _app_dir() / "hardware.json"


def _marker_file() -> Path:
    return _app_dir() / "loading.json"


def _crash_log() -> Path:
    return _app_dir() / "logs" / "crash.log"


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        log.warning("couldn't write %s", path.name)


# --------------------------------------------------------------------------- the machine

def physical_cores() -> int:
    env = os.environ.get("VOCET_CPU_CORES", "")
    if env.isdigit() and int(env) > 0:
        return int(env)
    import psutil
    return psutil.cpu_count(logical=False) or os.cpu_count() or 4


def cpu_threads() -> int:
    """Inference threads on the processor: one core stays free for the keyboard hook and the pill (S4)."""
    return max(1, physical_cores() - 1)


_affinity_done = False


def apply_core_limit() -> None:
    """VOCET_CPU_CORES=n also pins Vocet to n logical processors, so it really runs like a smaller PC."""
    global _affinity_done
    env = os.environ.get("VOCET_CPU_CORES", "")
    if _affinity_done or not env.isdigit() or int(env) < 1:
        return
    _affinity_done = True
    try:
        import psutil
        proc = psutil.Process()
        proc.cpu_affinity(proc.cpu_affinity()[: int(env)])
        log.info("VOCET_CPU_CORES=%s: limited to %d processors", env, len(proc.cpu_affinity()))
    except Exception:  # noqa: BLE001 - a test switch must never stop Vocet
        log.warning("couldn't apply VOCET_CPU_CORES")


def allowed_devices() -> set[str] | None:
    env = os.environ.get("VOCET_DEVICES", "").strip().lower()
    return {d.strip() for d in env.split(",") if d.strip()} if env else None


def simulated_failures() -> dict[str, str]:
    out = {}
    for part in os.environ.get("VOCET_PROBE_FAIL", "").lower().split(","):
        device, _, how = part.strip().partition(":")
        if device and how in ("raise", "hang", "crash"):
            out[device] = how
    return out


def openvino_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("openvino")
    except PackageNotFoundError:
        return ""


# --------------------------------------------------------------------------- the plan

@dataclass(frozen=True)
class Attempt:
    engine: str
    model: str
    device: str
    threads: int = 8

    @property
    def label(self) -> str:
        return f"{self.engine}/{self.model}/{self.device}"


def cpu_model(preset: dict, language, downloaded: Callable[[str], bool]) -> str:
    """The model a preset runs on the processor (settings.CPU_TIER). With a language other than
    English among the languages you speak (e.g. the default English + Deutsch) and a multilingual
    preset: the multilingual small on 4+ physical cores (German accuracy), base below that,
    large-v3-turbo only if neither is installed. English only: small.en / base.en by the same core
    rule. `language`: the languages list, or the old single setting ("auto" / "en" / "de")."""
    from .settings import CPU_TIER, needs_multilingual
    multilingual = bool(preset.get("multilingual")) and needs_multilingual(language)
    candidates = CPU_TIER["multilingual" if multilingual else "english"]
    if physical_cores() < CPU_TIER["small_min_cores_multilingual" if multilingual else "small_min_cores"]:
        candidates = (candidates[1], candidates[0], *candidates[2:])   # base first
    return next((m for m in candidates if downloaded(m)), preset["model"])


def plan(preset: dict, language="en", downloaded: Callable[[str], bool] | None = None) -> list[Attempt]:
    """Every (model, device) to try for a preset, best first. The last one is always the processor."""
    if downloaded is None:
        from . import engines
        downloaded = lambda m: m in engines.CATALOG[preset["engine"]] and engines.is_downloaded(preset["engine"], m)  # noqa: E731
    engine, model, threads = preset["engine"], preset["model"], cpu_threads()
    attempts = [Attempt(engine, model, d, threads) for d in dict.fromkeys([preset["device"], *ACCELERATORS])
                if d != "cpu" and (d != "npu" or model in NPU_MODELS)]
    attempts.append(Attempt(engine, cpu_model(preset, language, downloaded), "cpu", threads))
    return attempts


# --------------------------------------------------------------------------- bad devices, the marker

def bad_devices(now: float | None = None) -> dict[str, dict]:
    """Devices that crashed while loading, and aren't due for another try yet."""
    now, ver = now or time.time(), openvino_version()
    return {d: info for d, info in _read(_state_file()).get("bad", {}).items()
            if info.get("openvino") == ver and now - info.get("at", 0) < BAD_FOR_DAYS * 86400}


def mark_bad(device: str, reason: str, model: str = "") -> None:
    state = _read(_state_file())
    state.setdefault("bad", {})[device] = {"reason": reason, "model": model, "at": time.time(),
                                           "openvino": openvino_version()}
    state.get("unfinished", {}).pop(device, None)
    _write(_state_file(), state)
    log.warning("%s marked bad for %d days: %s", device, BAD_FOR_DAYS, reason)


def _crash_log_stat() -> tuple[int, float]:
    try:
        st = _crash_log().stat()
        return st.st_size, st.st_mtime
    except OSError:
        return 0, 0.0


_marker_lock = threading.Lock()
_stopping = threading.Event()   # set by stop_loading(): Vocet is quitting, start no new load


def _marker_add(a: Attempt) -> None:
    with _marker_lock:
        if _stopping.is_set():
            raise LoadCancelled("Vocet is quitting")
        m = _read(_marker_file())
        m.setdefault("crash_log_size", _crash_log_stat()[0])
        m.setdefault("loading", {})[a.device] = {"model": a.model, "at": time.time(), "pid": os.getpid()}
        _write(_marker_file(), m)


def _marker_remove(device: str) -> None:
    with _marker_lock:
        m = _read(_marker_file())
        m.get("loading", {}).pop(device, None)
        if m.get("loading"):
            _write(_marker_file(), m)
        else:
            try:
                _marker_file().unlink()
            except OSError:
                pass


def stop_loading() -> None:
    """Vocet is quitting on purpose: stop waiting for loads in progress, start no new one, and remove
    this process's entries from the marker. A deliberate quit isn't a crash, so it must never count
    towards marking a device bad. Loads already running inside a driver keep
    going on their daemon threads until the process ends; that's fine, nobody waits for them."""
    with _marker_lock:
        _stopping.set()
        m = _read(_marker_file())
        loading = m.get("loading", {})
        rest = {d: e for d, e in loading.items() if e.get("pid") != os.getpid()}
        if len(rest) == len(loading):
            return
        if rest:
            _write(_marker_file(), {**m, "loading": rest})
        else:
            try:
                _marker_file().unlink()
            except OSError:
                pass
        log.info("quitting: removed this process's loading marker (%s)", ", ".join(sorted(set(loading) - set(rest))))


def is_stopping() -> bool:
    """Vocet is quitting (stop_loading): a load step that waits on something should give up."""
    return _stopping.is_set()


def check_previous_start() -> list[str]:
    """Handles a marker left by an earlier process that died while loading. Returns the devices it
    marked bad. Entries from this process (a load that timed out and is still going) are kept."""
    with _marker_lock:
        m = _read(_marker_file())
        loading = m.get("loading", {})
        dead = {d: e for d, e in loading.items() if e.get("pid") != os.getpid()}
        if not dead:
            return []
        size, mtime = _crash_log_stat()
        started = min(e.get("at", 0) for e in dead.values())
        crashed = size > m.get("crash_log_size", 0) or (size > 0 and mtime >= started)
        state = _read(_state_file())
        unfinished = state.setdefault("unfinished", {})
        marked = []
        for device, e in dead.items():
            if crashed:
                reason = "Vocet crashed while loading on it"
            else:
                unfinished[device] = unfinished.get(device, 0) + 1
                if unfinished[device] < 2:
                    log.warning("the last start stopped while loading %s on %s (no crash logged); "
                                "trying it once more", e.get("model"), device)
                    continue
                reason = "Vocet stopped while loading on it twice in a row"
            state.setdefault("bad", {})[device] = {"reason": reason, "model": e.get("model", ""),
                                                   "at": time.time(), "openvino": openvino_version()}
            unfinished.pop(device, None)
            marked.append(device)
            log.warning("%s marked bad for %d days: %s", device, BAD_FOR_DAYS, reason)
        _write(_state_file(), state)
        rest = {d: e for d, e in loading.items() if d not in dead}
        if rest:
            _write(_marker_file(), {**m, "loading": rest})
        else:
            try:
                _marker_file().unlink()
            except OSError:
                pass
        return marked


def _loaded_ok(device: str) -> None:
    state = _read(_state_file())
    if state.get("unfinished", {}).pop(device, None) is not None:
        _write(_state_file(), state)


# --------------------------------------------------------------------------- loading

class LoadTimeout(TimeoutError):
    pass


class LoadCancelled(RuntimeError):
    """Vocet is quitting (stop_loading): the load was abandoned, not failed."""


class LoadFailed(RuntimeError):
    def __init__(self, failures: list, user_message: str):
        super().__init__("; ".join(f"{a.label}: {why}" for a, why in failures) or "nothing to try")
        self.failures, self.user_message = failures, user_message


@dataclass
class Loaded:
    transcriber: object
    attempt: Attempt
    note: str = ""                      # the sentence to show, or "" if the preset loaded as meant
    failures: list = field(default_factory=list)


def note_for(preferred: Attempt, used: Attempt) -> str:
    if used == preferred:
        return ""
    if used.device == "cpu":
        return MSG_CPU_SLOW if used.model in LARGE_MODELS else MSG_CPU
    return MSG_OTHER_CHIP


def _timeout(device: str, timeouts: dict | None) -> float:
    env = os.environ.get("VOCET_LOAD_TIMEOUT_S", "")
    try:
        return float(env) if env else (timeouts or LOAD_TIMEOUT_S).get(device, 120.0)
    except ValueError:
        return LOAD_TIMEOUT_S.get(device, 120.0)


def _late(a: Attempt, box: dict, done: threading.Event) -> None:
    done.wait()
    _marker_remove(a.device)
    if "result" in box:
        log.info("%s finished loading after its timeout; closed it (its compiled kernels are cached)", a.label)
        try:
            box["result"].close()
        except Exception:  # noqa: BLE001
            pass


def _attempt(a: Attempt, make: Callable[[Attempt], object], timeout: float, simulate: str | None):
    _marker_add(a)
    box: dict = {}
    done = threading.Event()

    def run() -> None:
        try:
            if simulate == "raise":
                raise RuntimeError(f"simulated failure on {a.device} (VOCET_PROBE_FAIL)")
            if simulate == "hang":
                threading.Event().wait()           # never returns: like a load stuck in a driver
            if simulate == "crash":
                import faulthandler
                faulthandler._read_null()          # a real access violation (0xC0000005), as from a driver
            box["result"] = make(a)
        except BaseException as exc:  # noqa: BLE001 - reported to the caller below
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=run, name=f"load-{a.device}", daemon=True).start()
    deadline = time.monotonic() + timeout
    while not done.wait(min(0.1, max(0.0, deadline - time.monotonic()))):
        if _stopping.is_set():      # quitting: don't keep the caller (the app's worker) waiting
            threading.Thread(target=_late, args=(a, box, done), name=f"late-{a.device}", daemon=True).start()
            raise LoadCancelled("Vocet is quitting")
        if time.monotonic() >= deadline:
            threading.Thread(target=_late, args=(a, box, done), name=f"late-{a.device}", daemon=True).start()
            raise LoadTimeout(f"didn't load within {timeout:.0f} s")
    _marker_remove(a.device)
    if "error" in box:
        raise box["error"]
    _loaded_ok(a.device)
    return box["result"]


def load(attempts: list[Attempt], make: Callable[[Attempt], object], timeouts: dict | None = None) -> Loaded:
    """Tries each attempt in order and returns the first that loads. Raises LoadFailed if none does."""
    check_previous_start()
    apply_core_limit()
    bad, allowed, sims = bad_devices(), allowed_devices(), simulated_failures()
    # Only an accelerator is ever skipped for a bad mark. The processor is the last resort: without
    # it a PC whose GPU just raises would get no speech at all for a week.
    usable = [a for a in attempts if (a.device == "cpu" or a.device not in bad)
              and (allowed is None or a.device in allowed)]
    if "cpu" in bad and any(a.device == "cpu" for a in usable):
        log.warning("the processor was marked bad (%s); trying it anyway, last, as the last resort",
                    bad["cpu"].get("reason", "?"))
    failures, damaged = [], set()
    for a in attempts:
        if a not in usable:
            why = f"skipped: {bad[a.device]['reason']}" if a.device in bad else "skipped: not on this PC (VOCET_DEVICES)"
            failures.append((a, why))
            log.info("%s %s", a.label, why)
            continue
        if a.model in damaged:
            failures.append((a, "skipped: model files damaged"))
            continue
        t0 = time.perf_counter()
        try:
            result = _attempt(a, make, _timeout(a.device, timeouts), sims.get(a.device))
        except LoadCancelled:
            raise                    # quitting: nothing more to try
        except ModelIntegrityError as exc:
            damaged.add(a.model)
            failures.append((a, f"integrity: {exc}"))
            log.error("refusing to load %s: %s", a.label, exc)
        except Exception as exc:  # noqa: BLE001 - any failure moves on to the next device
            failures.append((a, f"{type(exc).__name__}: {exc}"))
            log.warning("couldn't load %s after %.1f s (%s: %s); trying the next option",
                        a.label, time.perf_counter() - t0, type(exc).__name__, exc)
        else:
            note = note_for(attempts[0], a)
            if note:
                log.info("fell back to %s (%d threads): %s", a.label, a.threads, note)
            return Loaded(result, a, note, failures)
    only_damage = damaged and all(why.startswith(("integrity", "skipped")) for _, why in failures)
    raise LoadFailed(failures, ModelIntegrityError.user_message if only_damage else MSG_FAILED)
