"""Microphone capture and WAV files.

Everything after this module works on ONE format: 16 kHz, mono, float32 samples
in [-1, 1]. That's what every speech model here expects. Device sample rates and
channel counts are dealt with here and nowhere else.
"""

import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
import soxr

TARGET_RATE = 16_000


def _wasapi_index() -> int:
    # WASAPI is Windows' native audio API: full device names (MME truncates them
    # to 31 characters) and lower latency than MME/DirectSound.
    for i, api in enumerate(sd.query_hostapis()):
        if "WASAPI" in api["name"]:
            return i
    raise RuntimeError("WASAPI host API not found")


def list_input_devices() -> list[dict]:
    api = _wasapi_index()
    default = sd.query_hostapis(api)["default_input_device"]
    devices = []
    for index, d in enumerate(sd.query_devices()):
        if d["hostapi"] == api and d["max_input_channels"] > 0:
            devices.append({
                "index": index,
                "name": d["name"],
                "channels": d["max_input_channels"],
                "rate": int(d["default_samplerate"]),
                "default": index == default,
            })
    return devices


def default_input_device() -> int:
    return sd.query_hostapis(_wasapi_index())["default_input_device"]


def find_input_device(name: str | None) -> int:
    """Device index for a saved mic name. Indexes change when devices are plugged
    in or out, names don't. Falls back to the Windows default if it's gone."""
    if name:
        for d in list_input_devices():
            if d["name"] == name:
                return d["index"]
    return default_input_device()


def to_16k_mono(audio: np.ndarray, rate: int) -> np.ndarray:
    """Downmix (average channels) and resample to 16 kHz float32."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if rate != TARGET_RATE and len(audio):
        audio = soxr.resample(audio, rate, TARGET_RATE)
    return audio.astype(np.float32, copy=False)


class Recorder:
    """Records one input device into memory between start() and stop().

    Opening the device (__init__) costs 60-90 ms; start() on an open stream about
    6 ms (measured on a USB headset). The app opens a new Recorder on every key press
    anyway, so the mic is only in use while you dictate. PortAudio calls
    `_on_audio` on its own thread; it only does cheap work there (copy the block,
    compute its level), because anything heavier can cause dropouts.
    """

    def __init__(self, device: int | None = None):
        self.device = default_input_device() if device is None else device
        info = sd.query_devices(self.device)
        self.name = info["name"]
        self.rate = int(info["default_samplerate"])
        self.channels = info["max_input_channels"]
        self.overflows = 0
        self.level = 0.0  # RMS of the latest block, for the waveform
        self._blocks: list[np.ndarray] = []
        self._started_at = 0.0
        self.first_audio_latency_s: float | None = None
        # WASAPI shared mode only accepts the device's own mix rate/channels,
        # so we record in that format and convert afterwards.
        self._stream = sd.InputStream(
            device=self.device, samplerate=self.rate, channels=self.channels,
            dtype="float32", callback=self._on_audio,
        )

    def _on_audio(self, indata, frames, time_info, status):
        if status.input_overflow:
            self.overflows += 1
        if self.first_audio_latency_s is None:
            self.first_audio_latency_s = time.perf_counter() - self._started_at
        self._blocks.append(indata.copy())
        self.level = float(np.sqrt(np.mean(np.square(indata))))

    def start(self) -> None:
        self._blocks = []
        self.overflows = 0
        self.level = 0.0
        self.first_audio_latency_s = None
        self._started_at = time.perf_counter()
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Stops recording and returns 16 kHz mono float32 audio."""
        self._stream.stop()
        if not self._blocks:
            return np.zeros(0, dtype=np.float32)
        return to_16k_mono(np.concatenate(self._blocks), self.rate)

    def close(self) -> None:
        self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class WavRecorder:
    """Test stand-in for Recorder: plays back a WAV file as if it were being spoken
    into the mic (in real time), so the full app can be tested end to end without
    anyone talking. Only used when VOCET_TEST_WAV is set."""

    def __init__(self, path: Path):
        self.clip = load_wav(path)
        self.name = f"test file {Path(path).name}"
        self.overflows = 0
        self.first_audio_latency_s = 0.0
        self._t0 = None

    def _pos(self) -> int:
        return 0 if self._t0 is None else min(len(self.clip), int((time.perf_counter() - self._t0) * TARGET_RATE))

    @property
    def level(self) -> float:
        end = self._pos()
        window = self.clip[max(0, end - 800): end]
        return float(np.sqrt(np.mean(np.square(window)))) if len(window) else 0.0

    def start(self) -> None:
        self._t0 = time.perf_counter()

    def stop(self) -> np.ndarray:
        return self.clip[: self._pos()]

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


def save_wav(path, audio: np.ndarray) -> None:
    """Saves 16 kHz mono float32 audio as 16-bit PCM WAV (to a path or a binary file object)."""
    if isinstance(path, (str, Path)):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path = str(path)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_RATE)
        w.writeframes(pcm.tobytes())


def load_wav(path: Path) -> np.ndarray:
    """Loads a 16-bit PCM WAV (any rate/channels) as 16 kHz mono float32.

    Other formats (mp3, 24-bit, ...): convert first with
    `ffmpeg -i in.mp3 -ar 16000 -ac 1 -c:a pcm_s16le out.wav`.
    """
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: only 16-bit PCM WAV is supported (see load_wav docstring)")
        channels, rate = w.getnchannels(), w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    audio = pcm.astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels)
    return to_16k_mono(audio, rate)


def duration_s(audio: np.ndarray) -> float:
    return len(audio) / TARGET_RATE


def levels_dbfs(audio: np.ndarray) -> tuple[float, float]:
    """(peak, rms) in dBFS. 0 dBFS = full scale; speech is typically -30..-10 RMS."""
    if not len(audio):
        return -120.0, -120.0
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    to_db = lambda x: 20 * np.log10(max(x, 1e-6))
    return to_db(peak), to_db(rms)


def level_warning(audio: np.ndarray) -> str | None:
    peak, rms = levels_dbfs(audio)
    if peak > -0.5:
        return f"clipping (peak {peak:.1f} dBFS): move the mic away or lower input gain"
    if rms < -50:
        return f"very quiet (RMS {rms:.0f} dBFS): wrong mic, muted, or too far away?"
    return None
