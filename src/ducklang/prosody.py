"""表情通道：音域、音量、语速、粗糙度。绝不改动音节的音色 / 走势 / 时长类别。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .phonology import Syllable

# 语速和音域的安全范围：解码器的时长和走势阈值按这个范围留了余量
TEMPO_RANGE = (0.85, 1.2)
REGISTER_RANGE = (0.8, 1.3)


@dataclass(frozen=True)
class Voice:
    f0: float  # 基准音高（Hz）
    speed: float  # 语速
    rough: float  # 粗糙度 / 调幅深度倍率
    gain: float  # 音量
    am_rate: float = 34.0  # "嘎"的调幅频率（Hz）


VOICES: dict[str, Voice] = {
    "duckling": Voice(f0=330.0, speed=1.12, rough=0.75, gain=0.85, am_rate=40.0),
    "adult": Voice(f0=250.0, speed=1.0, rough=1.0, gain=0.9, am_rate=34.0),
    "angry": Voice(f0=270.0, speed=1.1, rough=1.35, gain=1.0, am_rate=42.0),
    "soft": Voice(f0=220.0, speed=0.9, rough=0.6, gain=0.75, am_rate=26.0),
}

EMOTIONS = ("neutral", "question", "excited", "alarm", "soft")

# 情绪 -> (音域, 音量, 语速, 粗糙度)
_EMOTION_SHAPES = {
    "neutral": (1.0, 1.0, 1.0, 1.0),
    "question": (1.05, 1.0, 0.95, 0.9),
    "excited": (1.12, 1.1, 1.08, 1.1),
    "alarm": (1.2, 1.2, 1.12, 1.3),
    "soft": (0.88, 0.8, 0.92, 0.7),
}


def get_voice(name: str) -> Voice:
    try:
        return VOICES[name]
    except KeyError as exc:
        raise ValueError(f"未知音色：{name}（可选：{', '.join(VOICES)}）") from exc


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


def adjust(syllable: Syllable, voice: Voice, emotion: str, *, emphasis: int = 0) -> Syllable:
    register, volume, tempo, rough = _EMOTION_SHAPES.get(emotion, _EMOTION_SHAPES["neutral"])
    # "很/太"只加重音量和音高，不拉长音节（时长是信息通道）
    volume *= 1.0 + 0.12 * emphasis
    register *= 1.0 + 0.04 * emphasis
    return replace(
        syllable,
        pitch=_clamp(register, REGISTER_RANGE),
        volume=volume * voice.gain,
        tempo=_clamp(tempo * voice.speed, TEMPO_RANGE),
        rough=rough * voice.rough,
    )
