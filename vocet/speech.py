"""From a finished recording to text: trim silence, split long audio, run the engine.

Silence handling is deliberately simple (frame energy, no ML model):
- Whisper invents text for silence ("Thank you." is a classic), so a recording
  with no speech-like energy is never sent to the model.
- Trimming leading/trailing silence makes every transcription a bit faster.

Long audio: Whisper works in 30-second windows, and OpenVINO's NPU pipeline
returns wrong text for audio longer than 30 s (measured 2026-09-28). So
anything over MAX_CHUNK_S is split at the quietest point near the limit, and the
pieces are transcribed in order.
"""

import logging
import time

import numpy as np

from .audio import TARGET_RATE
from . import engines

log = logging.getLogger(__name__)

FRAME_S = 0.03
MAX_CHUNK_S = 28.0


def _frame_db(audio: np.ndarray) -> np.ndarray:
    n = int(FRAME_S * TARGET_RATE)
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    rms = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-6))


def trim_silence(audio: np.ndarray, pad_s: float = 0.25, min_speech_s: float = 0.15,
                 floor_db: float = -50.0) -> np.ndarray | None:
    """Returns the speech part (plus padding), or None if there's no speech.

    A frame counts as speech if it's above -50 dBFS AND at least 10 dB above the
    recording's own noise floor (its quietest 10% of frames), so a noisy room
    doesn't count as speech.
    """
    db = _frame_db(audio)
    if not len(db):
        return None
    threshold = max(floor_db, float(np.percentile(db, 10)) + 10)
    voiced = np.flatnonzero(db > threshold)
    if len(voiced) * FRAME_S < min_speech_s:
        return None
    n = int(FRAME_S * TARGET_RATE)
    pad = int(pad_s * TARGET_RATE)
    start = max(0, voiced[0] * n - pad)
    end = min(len(audio), (voiced[-1] + 1) * n + pad)
    return audio[start:end]


def split_long(audio: np.ndarray, max_s: float = MAX_CHUNK_S) -> list[np.ndarray]:
    """Splits into pieces of at most max_s seconds, cutting at the quietest frame
    in the last 5 s before each limit (usually a pause between words)."""
    pieces, max_len, n = [], int(max_s * TARGET_RATE), int(FRAME_S * TARGET_RATE)
    while len(audio) > max_len:
        window = audio[max_len - 5 * TARGET_RATE: max_len]
        cut = max_len - 5 * TARGET_RATE + int(np.argmin(_frame_db(window))) * n + n // 2
        pieces.append(audio[:cut])
        audio = audio[cut:]
    pieces.append(audio)
    return pieces


AUTO_LANGUAGES = ("en", "de")   # the default "languages you speak" (settings.DEFAULT_LANGUAGES)
SHORT_S = 1.5                     # below this much speech, detection is a coin toss ("Ja." -> "Yeah.")
STICKY_S = 20 * 60                # ...so reuse the language you spoke in the last 20 minutes
# Simplified-Chinese initial prompt ("The following are sentences in Mandarin."). Without it Whisper
# writes Chinese with no punctuation at all; with it, CER 8.4 % -> 8.2 % (FLEURS). It
# must never be on for another language: left on, English WER went to 55 % and German to 51 %.
ZH_PROMPT = "以下是普通话的句子。"
_LEGACY = {"auto": ("en", "de")}  # the older single language setting


class Transcriber:
    """Runs a speech engine on one recording, including the language policy.

    languages = the languages you speak. One: always that language. Several: Whisper detects,
    choosing only among them (engine.set_allowed: a reduced lang_to_id, FLEURS `auto_set`:
    96-100 % right on French, Spanish, Chinese, 98 % Hindi). Safeguards:
      - very short recordings reuse the language you spoke most recently ("Ja." -> "Yeah.");
      - if the engine still picks a language outside your list (an engine that can't restrict
        detection), transcribe again in your most recent language, or your first one;
      - Chinese gets ZH_PROMPT, and only Chinese: detected as Chinese, it's transcribed again with it.
    """

    def __init__(self, engine: str = "openvino", model: str = "small.en", device: str = "npu", threads: int = 8):
        t0 = time.perf_counter()
        self._setup(engines.load_engine(engine, model, device, threads), f"{engine}/{model}/{device}")
        self.engine.transcribe(np.zeros(TARGET_RATE, dtype=np.float32))  # warm-up (first call is slow)
        log.info("loaded %s in %.2f s", self.name, time.perf_counter() - t0)

    @classmethod
    def around(cls, engine, name: str = "test", clock=time.monotonic) -> "Transcriber":
        """A Transcriber around an already-made engine (unit tests use a fake one)."""
        self = cls.__new__(cls)
        self._setup(engine, name, clock)
        return self

    def _setup(self, engine, name: str, clock=time.monotonic) -> None:
        self.engine, self.name, self.clock = engine, name, clock
        self.languages: tuple[str, ...] = ("en",)
        self.last_language: str | None = None
        self._last_at = 0.0
        self.detected = "en"          # language of the most recent transcription
        self._vocabulary = ""         # the dictionary hint (textproc.vocabulary_prompt)
        self._prompt: str | None = None

    @property
    def multilingual(self) -> bool:
        return not getattr(self.engine, "english_only", True)

    @property
    def language(self) -> str:
        """The old single setting's view: the one forced language, or "auto"."""
        return self.languages[0] if len(self.languages) == 1 else "auto"

    def set_vocabulary(self, words: list[str]) -> None:
        """Gives the dictionary to engines that support prompting (Whisper does, Parakeet doesn't)."""
        from .textproc import vocabulary_prompt
        self._vocabulary = vocabulary_prompt(words)
        self._prompt = None
        self._set_prompt(None)

    def set_languages(self, languages) -> None:
        """The languages you speak, e.g. ["en", "de", "fr"]. English-only models: always English."""
        codes = tuple(dict.fromkeys(c for c in languages or () if isinstance(c, str))) or ("en",)
        self.languages = codes if self.multilingual else ("en",)
        if hasattr(self.engine, "set_allowed"):
            self.engine.set_allowed(self.languages)

    def set_language(self, language: str) -> None:
        """The older single setting: "auto" (English + German) or one code."""
        self.set_languages(_LEGACY.get(language, (language,)))

    def _set_prompt(self, language: str | None) -> None:
        """The dictionary hint, plus ZH_PROMPT while (and only while) Chinese is transcribed."""
        if not hasattr(self.engine, "set_prompt"):
            return
        prompt = " ".join(p for p in (ZH_PROMPT if language == "zh" else "", self._vocabulary) if p)
        if prompt != self._prompt:
            self.engine.set_prompt(prompt)
            self._prompt = prompt

    def _run(self, pieces, language: str | None) -> str:
        from .textproc import join_pieces
        self._set_prompt(language)
        if hasattr(self.engine, "set_language"):
            self.engine.set_language(language)
        texts = []
        for piece in pieces:
            texts.append(self.engine.transcribe(piece))
            if language is None and hasattr(self.engine, "set_language"):
                language = getattr(self.engine, "detected", None)  # keep the rest of a long recording consistent
                if language not in self.languages:
                    language = None                              # never force one you don't speak
                self.engine.set_language(language)
        return join_pieces(texts)

    def transcribe(self, audio: np.ndarray) -> str:
        speech = trim_silence(audio)
        if speech is None:
            return ""
        pieces = split_long(speech)
        recent = self.last_language if self.clock() - self._last_at < STICKY_S else None
        if recent not in self.languages:
            recent = None
        if len(self.languages) == 1:
            forced = self.languages[0]
        elif len(speech) / TARGET_RATE < SHORT_S and recent:
            forced = recent
        else:
            forced = None
        text = self._run(pieces, forced)
        language = forced or getattr(self.engine, "detected", None) or self.languages[0]
        if language not in self.languages:
            fallback = recent or self.languages[0]
            log.info("Whisper detected %r; transcribing again in %s", language, fallback)
            language = fallback
            text = self._run(pieces, language)
        elif language == "zh" and not forced and hasattr(self.engine, "set_prompt"):
            text = self._run(pieces, "zh")   # again, with ZH_PROMPT (punctuation); only for Chinese
        self.detected = language
        self.last_language, self._last_at = language, self.clock()
        return text

    def close(self) -> None:
        self.engine.close()
