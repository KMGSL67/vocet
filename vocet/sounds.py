"""Soft start/stop ticks, generated in code (no audio files to license or ship).

Sound pairs with the visual pill, so feedback also works when you're not
looking at the screen ("Make sure all feedback is accessible").
Played with winsound (built into Python), asynchronously so it never delays dictation.
"""

import winsound
from pathlib import Path

import numpy as np

from .audio import save_wav, TARGET_RATE


def _tone(f0: float, f1: float, ms: int, gain_db: float = -26) -> np.ndarray:
    """A short pitch glide with a smooth envelope: reads as a 'tick', not a beep."""
    t = np.arange(int(TARGET_RATE * ms / 1000)) / TARGET_RATE
    freq = np.linspace(f0, f1, len(t))
    phase = 2 * np.pi * np.cumsum(freq) / TARGET_RATE
    env = np.sin(np.pi * np.clip(t / t[-1], 0, 1)) ** 2          # no clicks at start/end
    tone = np.sin(phase) + 0.25 * np.sin(2 * phase)               # a little warmth
    return (tone * env * 10 ** (gain_db / 20)).astype(np.float32)


class Sounds:
    def __init__(self, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        self.files = {
            "start": folder / "start.wav",
            "stop": folder / "stop.wav",
            "cancel": folder / "cancel.wav",
        }
        clips = {
            "start": _tone(660, 990, 70),
            "stop": _tone(990, 740, 80),
            "cancel": np.concatenate([_tone(520, 440, 60), np.zeros(600, np.float32), _tone(440, 360, 70)]),
        }
        for name, path in self.files.items():
            if not path.exists():
                save_wav(path, clips[name])
        self.enabled = True

    def play(self, name: str) -> None:
        if self.enabled:
            winsound.PlaySound(str(self.files[name]),
                               winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
