"""Model integrity: every model is pinned to one commit and checked against a SHA-256 manifest.

    vocet/models_manifest.json
        {"models": {"openvino/large-v3-turbo": {"repo": "OpenVINO/...", "revision": "<commit>",
                                                "files": {"openvino_encoder_model.bin": {"size": ..., "sha256": ...}}}}}

The key is the model's folder under models/. The manifest ships with Vocet's code, so the trust
chain runs from Vocet's own files to the model:

- `download()` (engines.py) fetches exactly the manifest's files at the pinned commit, nothing else
  (no upstream .py files), then verifies them.
- `verify()` runs before every load. A missing, resized or changed file raises ModelIntegrityError,
  and the model isn't loaded.
- Hashing is cheap after the first time: large-v3-turbo (790 MB) takes about 0.7 s to hash, so each
  file's result is remembered in the per-user data folder (model-hashes.json) under its size,
  modification time, file ID and creation time, and it's hashed again when any of them changes.
  A file replaced by another one (a copy, a download, a rename over it) gets a new file ID, even if
  its size and modification time were set back. A file changed in the same instant it was hashed
  isn't remembered at all (the "racily clean" case: file times only move every few milliseconds),
  which is what made tests/test_integrity.py fail now and then.

  What the cache doesn't catch, and why that's accepted: a program running
  as you can rewrite a model file *in place* and then set its modification time back (`os.utime`);
  size, file ID and creation time stay the same, so it isn't hashed again. It doesn't need to touch
  the cache for that. Such a program can equally rewrite Vocet's own code or the manifest, which
  are in folders you can write to as well, so hashing on every start wouldn't stop it. The hashes
  protect against damaged or incomplete downloads and against files changed by anything that
  doesn't also go out of its way to hide it. Files in a model folder that aren't in the manifest
  are never read by Vocet's loaders (they open fixed file names), so they aren't checked either.

The manifest was written from the metadata huggingface_hub leaves in each model folder (commit and
file list from .cache/huggingface/trees/<commit>.json, which also has Hugging Face's own SHA-256 for
every large file), after checking the local files against it.
"""

import fnmatch
import hashlib
import json
import logging
import threading
import time
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

MANIFEST_FILE = Path(__file__).with_name("models_manifest.json")
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

# What a model folder may contain, as downloaded: graphs and weights (OpenVINO IR .xml/.bin, ONNX,
# CTranslate2 model.bin, GGML .bin), tokenizer/config data and chat templates. Never code.
ALLOWED_TYPES = ("*.xml", "*.bin", "*.json", "*.txt", "*.jinja", "*.onnx", "*.model")
NEVER = ("*.py", "*.pyc", "*.pt", "*.pth", "*.pkl", "*.pickle", "*.ckpt", "*.safetensors",
         "pytorch_model*.bin", "*.exe", "*.dll", "*.so", "*.zip")

UNPINNED = "TODO"   # a manifest revision starting with this isn't pinned yet


class ModelIntegrityError(RuntimeError):
    """A model's files don't match the manifest. `str(exc)` is for the log (which file, why);
    `user_message` is the one sentence Vocet shows."""

    user_message = "The speech model’s files are damaged or were changed. Delete the models folder in Vocet’s folder, then restart Vocet to download it again."


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8")).get("models", {})


def entry(key: str) -> dict | None:
    return manifest().get(key)


def revision(key: str) -> str | None:
    """The pinned commit, or None if the manifest has no pinned one for this model."""
    rev = (entry(key) or {}).get("revision") or ""
    return None if not rev or rev.startswith(UNPINNED) else rev


def allowed_file(name: str) -> bool:
    base = name.rsplit("/", 1)[-1]
    return (any(fnmatch.fnmatch(base, p) for p in ALLOWED_TYPES)
            and not any(fnmatch.fnmatch(base, p) for p in NEVER))


def download_patterns(key: str) -> list[str]:
    """What a download may fetch: the manifest's exact files, or (for a model pinned to a commit
    but not hashed yet) only the allowed file types."""
    files = (entry(key) or {}).get("files") or {}
    return sorted(files) if files else list(ALLOWED_TYPES)


def sha256_file(path: Path, chunk: int = 8 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def present(key: str, folder: Path | None = None) -> bool:
    """Every manifest file is there with the right size (no hashing: for "is it downloaded?")."""
    files = (entry(key) or {}).get("files") or {}
    folder = folder or MODELS_DIR / key
    try:
        return bool(files) and all((folder / n).stat().st_size == f["size"] for n, f in files.items())
    except OSError:
        return False


# --------------------------------------------------------------------------- the hash cache

_lock = threading.Lock()
_memo: dict[str, list] = {}      # resolved path -> _stamp(st) + [sha256], this process
_memo_file: Path | None = None
RACY_NS = 2_000_000_000          # a file modified this recently before it was hashed isn't remembered


def _stamp(st) -> list:
    """What must be unchanged for a remembered hash to count: size, modification time, file ID
    (NTFS file index) and creation time (st_ctime on Windows)."""
    return [st.st_size, st.st_mtime_ns, st.st_ino, st.st_ctime_ns]


def _cache_file() -> Path:
    from . import settings   # read at call time: VOCET_HOME (tests) moves it
    return settings.APP_DIR / "model-hashes.json"


def _load_cache(path: Path) -> dict:
    global _memo, _memo_file
    if _memo_file != path:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _memo = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            _memo = {}
        _memo_file = path
    return _memo


def _save_cache(path: Path, cache: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=0), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        log.warning("couldn't save the model hash cache; files will be hashed again next time")


def verify(key: str, folder: Path | None = None, cache_file: Path | None = None) -> dict:
    """Checks a model folder against the manifest. Raises ModelIntegrityError on any problem.
    Returns {"files", "hashed", "bytes_hashed", "s"} for the log."""
    t0 = time.perf_counter()
    e = entry(key)
    if e is None:
        raise ModelIntegrityError(f"{key}: not in {MANIFEST_FILE.name}, so it can't be verified")
    if not revision(key) or not e.get("files"):
        raise ModelIntegrityError(f"{key}: not pinned and hashed in {MANIFEST_FILE.name} yet "
                                  "(pin its commit and hash its files first)")
    folder = Path(folder or MODELS_DIR / key)
    cache_file = cache_file or _cache_file()
    hashed = bytes_hashed = 0
    with _lock:
        cache = _load_cache(cache_file)
        changed = False
        for name, want in e["files"].items():
            path = folder / name
            try:
                st = path.stat()
            except OSError:
                raise ModelIntegrityError(f"{key}: {name} is missing") from None
            if st.st_size != want["size"]:
                raise ModelIntegrityError(f"{key}: {name} has {st.st_size} bytes, expected {want['size']}")
            ck = str(path.resolve())
            seen = cache.get(ck)
            if seen == [*_stamp(st), want["sha256"]]:
                continue                       # unchanged since it was last hashed and matched
            digest = sha256_file(path)
            hashed, bytes_hashed = hashed + 1, bytes_hashed + st.st_size
            if digest != want["sha256"]:
                cache.pop(ck, None)
                _save_cache(cache_file, cache)
                raise ModelIntegrityError(f"{key}: {name} doesn't match its SHA-256 in the manifest")
            if time.time_ns() - st.st_mtime_ns < RACY_NS:
                cache.pop(ck, None)            # it may change again within the same file-time tick
                continue
            cache[ck] = [*_stamp(st), digest]
            changed = True
        if changed:
            _save_cache(cache_file, cache)
    stats = {"files": len(e["files"]), "hashed": hashed, "bytes_hashed": bytes_hashed,
             "s": time.perf_counter() - t0}
    log.info("verified %s: %d files, %d hashed (%.0f MB) in %.3f s", key, stats["files"], hashed,
             bytes_hashed / 1e6, stats["s"])
    return stats


def forget_cache() -> None:
    """Drops this process's copy of the hash cache (tests)."""
    global _memo, _memo_file
    with _lock:
        _memo, _memo_file = {}, None


def git_blob_sha1(path: Path) -> str:
    """Git's id for a small (non-LFS) file, which Hugging Face lists as its blob_id."""
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
