from __future__ import annotations

from dataclasses import dataclass, replace

from .phonology import Syllable


@dataclass(frozen=True)
class Voice:
    f0: float
    speed: float
    rough: float
    gain: float


VOICES: dict[str, Voice] = {
    "duckling": Voice(f0=330.0, speed=1.15, rough=0.15, gain=0.9),
    "adult": Voice(f0=230.0, speed=1.0, rough=0.25, gain=0.9),
    "angry": Voice(f0=280.0, speed=1.2, rough=0.45, gain=1.0),
    "soft": Voice(f0=200.0, speed=0.85, rough=0.1, gain=0.7),
}

EMOTIONS = ("neutral", "question", "excited", "alarm", "soft")


def get_voice(name: str) -> Voice:
    try:
        return VOICES[name]
    except KeyError as exc:
        raise ValueError(f"未知音色：{name}（可选：{', '.join(VOICES)}）") from exc


def adjust(
    syllable: Syllable,
    voice: Voice,
    emotion: str,
    *,
    final: bool = False,
    emphasis: int = 0,
) -> Syllable:
    length = syllable.length * (1.0 + 0.18 * emphasis)
    pitch = syllable.pitch
    volume = syllable.volume * voice.gain

    if emotion == "question":
        length *= 1.06
        if final:
            pitch *= 1.28
    elif emotion == "alarm":
        length *= 0.86
        pitch *= 1.18
        volume *= 1.18
    elif emotion == "excited":
        length *= 0.92
        pitch *= 1.1
        volume *= 1.12
    elif emotion == "soft":
        length *= 1.14
        pitch *= 0.9
        volume *= 0.76

    if final:
        length *= 1.16

    return replace(
        syllable,
        length=length,
        pitch=pitch,
        volume=volume,
        emphasis=emphasis,
    )
