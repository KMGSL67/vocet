"""The speech engine: Whisper through OpenVINO GenAI.

The engine is wrapped behind a tiny interface:

    engine = load_engine("openvino", "small.en", device="gpu")
    text = engine.transcribe(audio)   # audio: 16 kHz mono float32 numpy array
    engine.close()

Models are downloaded once into models/<engine>/<model>/ (model_download.py) and always loaded
from that local path, so running never needs the network.

The first load of a model on a device is compiled in a helper process (`prepare`): OpenVINO GenAI's
WhisperPipeline holds Python's lock (the GIL) for its whole constructor, and the first compile for
a graphics card takes several seconds to a minute. Held in Vocet's own process, that froze the
window, the pill and the keyboard hook (all of them need the GIL) for as long as it took. The
helper fills the compiled-kernel cache instead; Vocet's own load then reads the cache, which still
holds the GIL, but for 1.3-2 s instead of the whole compile (large-v3-turbo on an Arc GPU,
measured 2026-10-08: the GIL held for 5.8 s in one go with an empty cache; with the helper, at most
2.0 s on the first launch and 1.3 s on later ones; the helper itself took 10 s, Python's start included).
"""

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import hardware, integrity, privacy

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"


@dataclass(frozen=True)
class ModelSpec:
    repo: str
    precision: str
    files: tuple[str, ...] = ()  # empty = whole repo
    english_only: bool = False


CATALOG: dict[str, dict[str, ModelSpec]] = {
    "openvino": {  # pre-converted by Intel, so the (telemetry-laden) converter is never needed
        "base.en": ModelSpec("OpenVINO/whisper-base.en-int8-ov", "int8", english_only=True),
        "small.en": ModelSpec("OpenVINO/whisper-small.en-int8-ov", "int8", english_only=True),
        "distil-large-v3": ModelSpec("OpenVINO/distil-whisper-large-v3-int8-ov", "int8"),
        "large-v3-turbo": ModelSpec("OpenVINO/whisper-large-v3-turbo-int8-ov", "int8"),
        # Multilingual processor tiers (settings.CPU_TIER): German without a working GPU/NPU.
        # Pinned in models_manifest.json.
        "small": ModelSpec("OpenVINO/whisper-small-int8-ov", "int8"),
        "base": ModelSpec("OpenVINO/whisper-base-int8-ov", "int8"),
    },
}

DEVICES = {
    "openvino": ["cpu", "gpu", "npu"],
}


def model_dir(engine: str, model: str) -> Path:
    return MODELS_DIR / engine / model


def is_downloaded(engine: str, model: str) -> bool:
    """Every file the manifest lists is there with the right size (no hashing; load_engine hashes).
    A model the manifest hasn't hashed yet counts as downloaded if its folder isn't empty."""
    key = f"{engine}/{model}"
    if (integrity.entry(key) or {}).get("files"):
        return integrity.present(key)
    d = model_dir(engine, model)
    return d.is_dir() and any(d.iterdir())


# --------------------------------------------------------------------------- engine

class OpenVinoWhisper:
    def __init__(self, model: str, device: str, threads: int, beam: int):
        privacy.disable_openvino_telemetry()  # must happen before the import below
        import openvino_genai

        self.pipe = openvino_genai.WhisperPipeline(str(model_dir("openvino", model)), device.upper(),
                                                   **compile_props(device, threads))
        self.config = self.pipe.get_generation_config()
        self.english_only = CATALOG["openvino"][model].english_only
        self._all_languages: dict = {}
        if not self.english_only:
            self.config.language = "<|en|>"
            self.config.task = "transcribe"   # never "translate": German stays German
            self._all_languages = dict(self.config.lang_to_id)
        self.detected = "en"
        self.config.num_beams = beam
        self.config.return_timestamps = False
        self.pid = os.getpid()

    def set_prompt(self, prompt: str) -> None:
        """Hint words (the Vocet dictionary) that Whisper should expect to hear."""
        self.config.initial_prompt = prompt or None

    def set_language(self, code: str | None) -> None:
        """'en', 'de', ... or None to detect it. English-only models always use English."""
        if not self.english_only:
            self.config.language = f"<|{code}|>" if code else None

    def set_allowed(self, codes) -> None:
        """Detection chooses only among these languages (the languages you speak): a reduced
        lang_to_id. None = all of Whisper's.
        A forced language must be in the map (OpenVINO refuses one that isn't), so force only these."""
        if self.english_only:
            return
        reduced = {f"<|{c}|>": self._all_languages[f"<|{c}|>"] for c in codes or ()
                   if f"<|{c}|>" in self._all_languages}
        self.config.lang_to_id = reduced or self._all_languages

    def transcribe(self, audio: np.ndarray) -> str:
        result = self.pipe.generate(audio, self.config)
        lang = result.language if isinstance(result.language, str) else (list(result.language) or [""])[0]
        self.detected = (lang or "").strip("<|>") or "en"   # Whisper reports e.g. "de"
        return str(result.texts[0]).strip()

    def close(self) -> None:
        del self.pipe


_ENGINES = {"openvino": OpenVinoWhisper}


def compile_props(device: str, threads: int) -> dict:
    """WhisperPipeline's properties. The helper (prepare) and Vocet's own load must pass the same
    ones, or the cache the helper filled doesn't match and Vocet compiles everything again."""
    props = {"CACHE_DIR": str(hardware.cache_dir())}  # compiled kernels: per user, never the install folder
    if device == "cpu":
        props["INFERENCE_NUM_THREADS"] = threads
    return props


# --------------------------------------------------------------------------- the first compile

PREPARED_FILE = "prepared.json"   # in the cache folder, so emptying the cache forgets it too
NATIVE_CRASH = 0xC0000000         # exit codes from here up are Windows exceptions (e.g. 0xC0000005), not Python's

# The helper process: the same Python and packages as Vocet (vocet.pyw adds the .venv's packages
# itself, so the parent's sys.path is passed on), offline like Vocet, and it only builds the
# pipeline. os._exit skips tearing the pipeline down again: nothing in it is needed after the cache.
_HELPER = """\
import json, os, site, sys
job = json.loads(sys.argv[1])
for p in job["path"]:
    if p not in sys.path:
        site.addsitedir(p)
from vocet import privacy
privacy.lock_down()
import openvino_genai
openvino_genai.WhisperPipeline(job["model_dir"], job["device"], **job["props"])
os._exit(0)
"""


def _prepared_stamp(device: str, threads: int) -> dict:
    """What a cached compile depends on, besides the model and the device."""
    return {"openvino": hardware.openvino_version(), "threads": threads if device == "cpu" else None}


def is_prepared(engine: str, model: str, device: str, threads: int = 8) -> bool:
    """This model was compiled for this device (by this OpenVINO) before: its kernels are cached,
    so loading it takes seconds, not up to a minute. Cheap: reads one small file."""
    data = hardware._read(hardware.cache_dir() / PREPARED_FILE)
    return data.get(f"{engine}/{model}/{device}") == _prepared_stamp(device, threads)


def _mark_prepared(engine: str, model: str, device: str, threads: int) -> None:
    path = hardware.cache_dir() / PREPARED_FILE
    data = hardware._read(path)
    data[f"{engine}/{model}/{device}"] = _prepared_stamp(device, threads)
    hardware._write(path, data)


def _helper_command(job: dict) -> list[str]:
    return [sys.executable, "-c", _HELPER, json.dumps(job)]


def prepare(engine: str, model: str, device: str, threads: int = 8) -> None:
    """The first time a model loads on a device, compile it in a helper process (see the module
    docstring for why). Waits for it without holding the GIL. Nothing to do once it's cached.

    A helper that can't start or fails is logged and the load goes on in Vocet's own process, as it
    did before (the window then freezes while it compiles, but speech works). A helper that crashed
    in native code (a driver fault) raises instead, so hardware.load moves on to the next device
    rather than crashing Vocet the same way. Quitting stops the helper."""
    if is_prepared(engine, model, device, threads):
        return
    job = {"path": [p for p in sys.path if p], "model_dir": str(model_dir(engine, model)),
           "device": device.upper(), "props": compile_props(device, threads)}
    t0 = time.perf_counter()
    try:
        proc = subprocess.Popen(_helper_command(job), cwd=str(ROOT), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                # no terminal window; and the compile gives way to what you're doing
                                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    except OSError as exc:
        log.warning("couldn't start the helper that compiles the speech model (%s); compiling in Vocet", exc)
        return
    log.info("compiling %s/%s for %s the first time, in a helper process", engine, model, device)
    while True:
        try:
            code = proc.wait(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            if hardware.is_stopping():
                proc.kill()
                raise hardware.LoadCancelled("Vocet is quitting") from None
    seconds = time.perf_counter() - t0
    if code == 0:
        log.info("compiled %s/%s for %s in %.1f s", engine, model, device, seconds)
    elif code >= NATIVE_CRASH:
        raise RuntimeError(f"the helper compiling it crashed after {seconds:.1f} s (exit code 0x{code:08X})")
    else:
        log.warning("the helper compiling %s/%s for %s stopped with exit code %d after %.1f s; "
                    "compiling in Vocet", engine, model, device, code, seconds)


def load_engine(engine: str, model: str, device: str = "cpu", threads: int = 8, beam: int = 1):
    if model not in CATALOG[engine]:
        raise ValueError(f"unknown model {model!r} for {engine}; choose from {list(CATALOG[engine])}")
    if device not in DEVICES[engine]:
        raise ValueError(f"{engine} supports devices {DEVICES[engine]}, not {device!r}")
    if not is_downloaded(engine, model):
        raise FileNotFoundError(f"{engine}/{model} is not downloaded; open Vocet to download it")
    integrity.verify(f"{engine}/{model}", model_dir(engine, model))   # pinned + SHA-256, before any file is parsed
    prepare(engine, model, device, threads)                            # the first compile, outside Vocet's process
    made = _ENGINES[engine](model, device, threads, beam)
    _mark_prepared(engine, model, device, threads)
    return made
