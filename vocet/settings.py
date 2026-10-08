"""Vocet's settings: one JSON file in %LOCALAPPDATA%\\Vocet\\settings.json.

Defaults are chosen so most people never open Settings ("Aim
to provide default settings that give the best experience to the largest number
of people"). Unknown keys in the file are kept; missing ones fall back to DEFAULTS.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

# VOCET_HOME: a separate data folder, used by automated tests so they never touch your real history.
APP_DIR = Path(os.environ.get("VOCET_HOME") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Vocet")
SETTINGS_FILE = APP_DIR / "settings.json"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# "device" is where a preset runs best; hardware.plan() falls back to the other chips and finally
# to the processor (CPU_TIER) if it doesn't load there. No speeds in "detail": they
# depend on the PC.
MODEL_PRESETS = {
    "fast": {"engine": "openvino", "model": "small.en", "device": "npu", "multilingual": False,
             "label": "Fast", "detail": "English only. The smallest model."},
    "balanced": {"engine": "openvino", "model": "distil-large-v3", "device": "gpu", "multilingual": False,
                 "label": "Balanced", "detail": "English only. More accurate than Fast."},
    "accurate": {"engine": "openvino", "model": "large-v3-turbo", "device": "gpu", "multilingual": True,
                 "label": "Most accurate", "detail": "Fewest mistakes. Needed for German and other languages."},
}

# The processor tier: what a preset runs when no graphics chip or NPU works. The first
# installed model is used. Measured on one laptop's CPU (8 threads, 3-8 s
# clips): base.en 0.28 s, small.en 0.81 s, large-v3-turbo 3.4 s. small.en needs about 6 physical
# cores to stay under a second (est.); below that, base.en comes first. Threads: one fewer than the
# physical cores (hardware.cpu_threads), so the keyboard hook and the pill keep a core.
# German on (or English + Deutsch): the multilingual small from 4 cores (base's German WER is 13.4 %
# against small's 3.4 %, so accuracy wins over the extra second), base only below 4. Same rule idea
# (small 1.3 s at 7 threads with the CPU half busy, turbo 5.6 s).
# large-v3-turbo stays last: slow, but it works if neither is installed. English only keeps the
# .en models: as fast as small/base and more accurate in English.
CPU_TIER = {
    "english": ("small.en", "base.en"),
    "multilingual": ("small", "base", "large-v3-turbo"),
    "small_min_cores": 6,
    "small_min_cores_multilingual": 4,
}

# Push-to-talk hotkeys: (groups of keys, label). One key from each group must be held (hotkey.py).
# The sentences the user reads about each key live in ui/SettingsPage.qml, not here.
_CTRL, _WIN = (0xA2, 0xA3), (0x5B, 0x5C)
HOTKEYS = {
    "ctrlwin": ((_CTRL, _WIN), "Ctrl + Win"),
    "rctrl": (((0xA3,),), "Right Ctrl"),
    "ralt": (((0xA5,),), "Right Alt"),
    "menu": (((0x5D,),), "Menu key"),
    "scroll": (((0x91,),), "Scroll Lock"),
    "pause": (((0x13,),), "Pause"),
}

# Languages you speak: Whisper detects among only these, and with one it's forced (speech.py).
# (code, name in its own language, note). Order = the order everywhere (menu, summary, settings.json).
SPOKEN_LANGUAGES = [
    ("en", "English", ""), ("de", "Deutsch", ""), ("fr", "Français", ""), ("es", "Español", ""),
    ("zh", "中文", "Simplified Chinese"), ("hi", "हिन्दी", "Beta"),
]
LANGUAGE_CODES = tuple(code for code, _, _ in SPOKEN_LANGUAGES)
DEFAULT_LANGUAGES = ["en", "de"]

# The older single "language" setting ("auto" = English + German). Still written, in step
# with "languages", so an older copy sharing settings.json reads something sensible (legacy_language).
LANGUAGES = [("auto", "English + Deutsch (automatic)"), ("en", "English"), ("de", "Deutsch")]
FROM_LEGACY = {"auto": ["en", "de"], "en": ["en"], "de": ["de"]}


def normalize_languages(value) -> list[str] | None:
    """A valid languages list in canonical order, duplicates dropped; None if it isn't one
    (not a list, an unknown code, or empty: at least one language must stay chosen)."""
    if not isinstance(value, (list, tuple)) or not all(isinstance(c, str) for c in value):
        return None
    if not value or any(c not in LANGUAGE_CODES for c in value):
        return None
    return [c for c in LANGUAGE_CODES if c in value]


def legacy_language(languages: list[str]) -> str:
    """The old single setting that best matches a languages list (for an older copy of the app)."""
    return {("en",): "en", ("de",): "de"}.get(tuple(languages), "auto")


def needs_multilingual(languages) -> bool:
    """Any language but English needs a multilingual model (the English-only presets can't)."""
    if isinstance(languages, str):  # the old single setting
        return languages != "en"
    return any(code != "en" for code in languages)

HISTORY_OPTIONS = [(0, "Don't keep history"), (1, "1 day"), (7, "7 days"), (30, "30 days"), (None, "Forever")]

DEFAULTS = {
    "mic": None,                 # None = Windows default microphone
    "preset": "accurate",
    "languages": list(DEFAULT_LANGUAGES),  # the languages you speak; detected among these per dictation
    "language": "auto",          # the older single setting, kept in step with "languages" (legacy_language)
    "hotkey": "ctrlwin",
    "hands_free": True,          # Space while holding (combos) / double-tap (single keys)
    "remove_fillers": True,
    "sounds": True,
    "show_idle": False,          # the small bar at the bottom of the screen; off = Vocet only appears while you dictate
    "accent": "violet",          # brand.ACCENTS; violet by default
    "theme": "graphite",         # v2 colour theme: read only to migrate older files (graphite = mono)
    "history_days": 30,
    "start_with_windows": False,
    "dictionary": [],            # [{"term": "Kubernetes", "heard": ""}, ...]
    "snippets": [],              # [{"trigger": "my email", "text": "..."}, ...]
    "ai_formatting": False,      # local AI formatting (ai_format.py); off until you switch it on
    "settings_version": 2,      # 1 (or missing): written before v4; see load()
    "welcomed_version": 0,       # the first-run welcome you've seen (WELCOME_VERSION); 0 = not yet
}
SETTINGS_VERSION = DEFAULTS["settings_version"]
# The first-run welcome (ui/Welcome.qml). Raise it only if a new welcome is worth showing
# to everyone again; a missing key in an existing settings.json means "used Vocet before the welcome".
WELCOME_VERSION = 1


# v2 colour themes -> the v3 accents that replaced them (Mono replaced Graphite).
THEME_TO_ACCENT = {"violet": "violet", "aurora": "violet", "ocean": "blue", "forest": "teal", "graphite": "mono"}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# Values that need more than "same type as the default". Looked up at load time, so a
# changed MODEL_PRESETS / HOTKEYS / LANGUAGES is picked up automatically.
_CHECKS = {
    "mic": lambda v: v is None or isinstance(v, str),
    "preset": lambda v: isinstance(v, str) and v in MODEL_PRESETS,
    "language": lambda v: isinstance(v, str) and v in {code for code, _ in LANGUAGES},
    "languages": lambda v: normalize_languages(v) is not None,
    "hotkey": lambda v: isinstance(v, str) and v in HOTKEYS,
    "history_days": lambda v: v is None or (_is_int(v) and 0 <= v <= 36500),
}

# Lists of entries: a bad entry is dropped, the good ones are kept.
_LIST_ENTRIES = {
    "dictionary": lambda w: isinstance(w, dict) and isinstance(w.get("term"), str) and bool(w["term"].strip())
    and isinstance(w.get("heard", ""), str),
    "snippets": lambda s: isinstance(s, dict) and isinstance(s.get("trigger"), str) and isinstance(s.get("text"), str),
}


def _valid(key: str, value) -> bool:
    if key in _CHECKS:
        return _CHECKS[key](value)
    default = DEFAULTS[key]
    if default is None:
        return True
    if isinstance(default, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return type(value) is type(default)  # bool is not accepted for int, nor int for bool


def validate(data: dict, problems: list | None = None) -> dict:
    """DEFAULTS, overridden by each value from the file that is valid. A bad value falls back to
    that key's default instead of stopping Vocet from starting. Only key names are logged,
    never values (they can be your dictionary words or snippet text). `problems` collects the
    names of keys that were changed or dropped, so load() can keep a copy of the file first."""
    problems = [] if problems is None else problems
    settings = dict(DEFAULTS)
    for key, value in data.items():
        if key not in DEFAULTS:
            settings[key] = value  # unknown keys are kept (a newer Vocet may use them)
        elif key in _LIST_ENTRIES:
            if not isinstance(value, list):
                log.warning("settings.json: '%s' isn't a list; using the default", key)
                problems.append(key)
                continue
            good = [{**({"heard": ""} if key == "dictionary" else {}), **entry}
                    for entry in value if _LIST_ENTRIES[key](entry)]
            if len(good) != len(value):
                log.warning("settings.json: dropped %d invalid '%s' entries", len(value) - len(good), key)
                problems.append(key)
            settings[key] = good
        elif _valid(key, value):
            settings[key] = normalize_languages(value) if key == "languages" else value
        else:
            log.warning("settings.json: '%s' has an invalid value; using the default", key)
            problems.append(key)
    return settings


BACKUPS_KEPT = 5
_keep_file = False   # the file couldn't be read *or* copied: save() must not replace it this session


def _backup(raw: bytes, why: str) -> bool:
    """Keeps a copy of a settings file Vocet couldn't fully use (settings.json.bad-<time>), before
    anything can save over it: your dictionary and snippets stay recoverable. The newest
    BACKUPS_KEPT copies are kept; an identical copy isn't made twice. True if the copy exists."""
    folder = SETTINGS_FILE.parent
    old = sorted(folder.glob(SETTINGS_FILE.name + ".bad-*"))
    try:
        if old and old[-1].read_bytes() == raw:
            return True                    # the same broken file as last start: already kept
        path = folder / f"{SETTINGS_FILE.name}.bad-{time.strftime('%Y%m%d-%H%M%S')}"
        n = 1
        while path.exists():
            path, n = folder / f"{SETTINGS_FILE.name}.bad-{time.strftime('%Y%m%d-%H%M%S')}-{n}", n + 1
        path.write_bytes(raw)
    except OSError:
        log.error("settings.json %s, and a copy of it couldn't be kept", why)
        return False
    log.warning("settings.json %s; kept a copy as %s before using the defaults", why, path.name)
    for extra in sorted(folder.glob(SETTINGS_FILE.name + ".bad-*"))[:-BACKUPS_KEPT]:
        try:
            extra.unlink()
        except OSError:
            pass
    return True


def _read_settings_bytes() -> bytes | None:
    """The file's bytes, or None if there is no file. A file another program holds for a moment
    (antivirus, the search indexer) is read again a few times before giving up."""
    for attempt in range(3):
        try:
            return SETTINGS_FILE.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.1)
    return None


def load() -> dict:
    """The settings from settings.json. Never loses what's in the file:
    a UTF-8 BOM (Notepad, PowerShell 5.1) is fine; a file that can't be parsed, or whose values
    had to be reset, is copied to settings.json.bad-<time> first, since the next change saves the
    defaults over it; and a file that can't even be read is never replaced this session."""
    global _keep_file
    _keep_file = False
    existed, raw = True, b""
    try:
        raw = _read_settings_bytes()
        if raw is None:
            data, existed = {}, False
        else:
            data = json.loads(raw.decode("utf-8-sig"))
    except OSError:
        log.error("settings.json couldn't be read; using the defaults, and it won't be saved over this session")
        _keep_file = True
        data = {}
    except ValueError:   # not JSON, not UTF-8, or empty
        if raw.strip() and not _backup(raw, "couldn't be read"):
            _keep_file = True
        data = {}
    if not isinstance(data, dict):
        if raw.strip() and not _backup(raw, "isn't a JSON object"):
            _keep_file = True
        data = {}
    problems: list = []
    settings = validate(data, problems)
    if problems and not _backup(raw, "had values Vocet couldn't use"):
        _keep_file = True
    if normalize_languages(data.get("languages")) is None:
        # A file from before "languages you speak" (or a broken list): the old single setting
        # decides ("auto" = English + Deutsch, the default), so nobody's choice is lost.
        settings["languages"] = list(FROM_LEGACY.get(settings["language"], DEFAULT_LANGUAGES))
    settings["language"] = legacy_language(settings["languages"])
    if "accent" not in data and "theme" in data:  # a file from before accents: its theme picks the accent
        settings["accent"] = THEME_TO_ACCENT.get(settings["theme"], "mono")
    version = data.get("settings_version")
    if not _is_int(version) or version < 2:
        # v3 saved every setting, defaults included, so its "mono" can't be told apart from a
        # choice: a file from before v4 with mono gets v4's default, violet. Any other
        # accent was picked on purpose and stays. From version 2 on, whatever is saved is kept.
        if settings["accent"] == "mono":
            settings["accent"] = DEFAULTS["accent"]
        settings["settings_version"] = SETTINGS_VERSION
    if existed and "welcomed_version" not in data:
        # A settings file from before the welcome existed: you've used Vocet already, so it
        # isn't shown. Brand-new users have no file at all.
        settings["welcomed_version"] = WELCOME_VERSION
    return settings


def save(settings: dict) -> None:
    if _keep_file:
        log.warning("not saving settings.json: the file there couldn't be read or copied, so it's left as it is")
        return
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(settings, indent=2, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())    # on disk before the rename: a power cut can't leave an empty file
    tmp.replace(SETTINGS_FILE)  # atomic: a crash mid-write can't leave a half-written file


def windowless_python() -> Path:
    """Python's own pythonw.exe (a GUI program, so no terminal window opens).
    Not the venv's copy: uv's venv launcher is a console program (see vocet.pyw)."""
    return Path(sys.base_prefix) / "pythonw.exe"


def launch_command() -> str:
    """How Windows should start Vocet: the windowless Python running vocet.pyw."""
    return f'"{windowless_python()}" "{PROJECT_ROOT / "vocet.pyw"}"'


TEST_AUTOSTART_FILE = "start-with-windows.test.txt"
RUN_VALUE = "Vocet"   # the value name under HKCU\...\Run


def set_start_with_windows(enabled: bool) -> None:
    """Adds or removes Vocet in the HKCU Run key. A test instance (VOCET_HOME set) never touches the
    registry: the entry is yours, and a test deleting it would turn off your autostart.
    It writes the would-be entry to a file in its own folder instead."""
    if os.environ.get("VOCET_HOME"):
        fake = Path(os.environ["VOCET_HOME"]) / TEST_AUTOSTART_FILE
        if enabled:
            fake.parent.mkdir(parents=True, exist_ok=True)
            fake.write_text(launch_command(), encoding="utf-8")
        else:
            fake.unlink(missing_ok=True)
        log.info("test instance: Start with Windows %s in %s, not in the registry", "on" if enabled else "off", fake.name)
        return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass
