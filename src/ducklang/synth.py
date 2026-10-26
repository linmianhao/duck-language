"""采样 + 程序化混合鸭叫合成（源 - 滤波模型）。

- 声源（程序化）：谐波丰富的脉冲序列，基频曲线由走势和时长精确生成 —— 承载信息，保证可解码；
- 粗糙度（程序化）：20–45 Hz 深度调幅 + 抖动 —— "嘎"的沙哑感；
- 声道滤波（真实录音）：data/voice_bank.npz 里从真实鸭叫提取的亮 / 暗频谱包络；
- 起音（真实录音）：真实鸭叫开头约 15 ms 的瞬态，交叉淡入。
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from .ir import TranslationResult
from .lexicon import data_dir
from .phonology import TAIL_WORD, Syllable, parse_word
from .prosody import Voice, adjust, get_voice

SR = 48_000

# 时长（秒，tempo = 1 时）；长音 ≥ 2.4 倍短音，解码阈值在两者之间
SHORT_S = 0.15
LONG_S = 0.36
# 静音（秒）：词内音节 / 词间 / 子句间，解码器靠它们切分
GAP_SYLLABLE = 0.060
GAP_WORD = 0.200
GAP_CLAUSE = 0.500

# 走势：基频倍率关键点 (相对时间, 倍率)。降 / 升 首尾相差约 ±8 个半音，平 ≤ 0.5 个半音
# 降调开头有一个很短的上冲（"嘎~"），只占前 10%，不影响整体斜率
CONTOUR_SHAPES = {
    "a": ((0.0, 1.16), (0.1, 1.25), (1.0, 0.76)),
    "i": ((0.0, 0.80), (1.0, 1.25)),
    "o": ((0.0, 1.0), (1.0, 0.98)),
}
TARGETS = ("pc", "robot")


@dataclass(frozen=True)
class VoiceBank:
    grid: np.ndarray
    bright: np.ndarray
    dark: np.ndarray
    attacks: np.ndarray
    from_samples: bool

    def envelope(self, timbre: str) -> np.ndarray:
        return self.bright if timbre == "k" else self.dark


def _builtin_bank() -> VoiceBank:
    """没有采样库时的程序化包络（两组鸭喙共振峰）。"""
    grid = np.linspace(0.0, SR / 2, 513)

    def peaks(*bands: tuple[float, float, float]) -> np.ndarray:
        env = 0.02 + np.zeros_like(grid)
        for center, width, gain in bands:
            env += gain * np.exp(-0.5 * ((grid - center) / width) ** 2)
        return env / env.max()

    bright = peaks((1950, 380, 1.0), (3300, 600, 0.45), (900, 250, 0.15))
    dark = peaks((1180, 300, 1.0), (2300, 500, 0.35), (600, 200, 0.2))
    return VoiceBank(grid, bright, dark, np.zeros((0, 0)), from_samples=False)


@lru_cache(maxsize=2)
def load_bank(path: str | None = None) -> VoiceBank:
    try:
        bank_path = Path(path) if path else data_dir() / "voice_bank.npz"
        if bank_path.exists():
            with np.load(bank_path) as data:
                return VoiceBank(
                    grid=data["grid"].astype(np.float64),
                    bright=data["bright"].astype(np.float64),
                    dark=data["dark"].astype(np.float64),
                    attacks=data["attacks"].astype(np.float64),
                    from_samples=True,
                )
    except (OSError, KeyError, ValueError):
        pass
    return _builtin_bank()


def syllable_duration(syllable: Syllable) -> float:
    return (LONG_S if syllable.long else SHORT_S) / syllable.tempo


def _f0_curve(syllable: Syllable, voice: Voice, n: int, rng: np.random.Generator) -> np.ndarray:
    pos = np.linspace(0.0, 1.0, n)
    points = CONTOUR_SHAPES[syllable.contour]
    shape = np.interp(pos, [p[0] for p in points], [p[1] for p in points])
    # 抖动 ≤ ±0.15 个半音，远小于走势阈值
    wobble = np.convolve(rng.normal(size=n), np.ones(480) / 480, mode="same")
    wobble = wobble / (np.max(np.abs(wobble)) + 1e-9) * 0.15
    return voice.f0 * syllable.pitch * shape * 2.0 ** (wobble / 12.0)


def _source(f0: np.ndarray, rng: np.random.Generator, subharmonic: float) -> np.ndarray:
    phase = 2.0 * np.pi * np.cumsum(f0) / SR
    n_harm = int(11_000 / float(np.max(f0)))
    source = np.zeros_like(f0)
    for k in range(1, n_harm + 1):
        source += np.sin(k * phase) / k**0.55
    # 周期加倍（相邻两个周期一强一弱）：鸭叫"嘎"的破音感主要来自这里
    source *= 1.0 - subharmonic * (0.5 + 0.5 * np.cos(phase / 2.0))
    # 每个周期的幅度微抖（shimmer），让声音不那么"电子"
    shimmer = 1.0 + 0.06 * np.convolve(rng.normal(size=len(f0)), np.ones(96) / 96, mode="same")
    return source * shimmer


def _apply_envelope(signal: np.ndarray, bank: VoiceBank, timbre: str) -> np.ndarray:
    n = len(signal)
    n_fft = 1 << int(np.ceil(np.log2(n + 2048)))
    spec = np.fft.rfft(signal, n_fft)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / SR)
    env = np.interp(freqs, bank.grid, bank.envelope(timbre))
    return np.fft.irfft(spec * env, n_fft)[:n]


def synth_syllable(
    syllable: Syllable,
    voice: Voice,
    *,
    seed: int = 7,
    bank: VoiceBank | None = None,
) -> np.ndarray:
    bank = bank or load_bank()
    rng = np.random.default_rng(seed)
    dur = syllable_duration(syllable)
    n = int(SR * dur)
    t = np.arange(n) / SR

    bright = syllable.timbre == "k"
    rough = min(1.2, syllable.rough)
    f0 = _f0_curve(syllable, voice, n, rng)
    body = _source(f0, rng, subharmonic=(0.45 if bright else 0.3) * rough)

    # 调幅：亮音色更深，暗音色更圆；上限 0.8，太深会让解码器把一声切成两段
    depth = min(0.8, (0.75 if bright else 0.45) * rough)
    am = 1.0 - depth * (0.5 + 0.5 * np.sin(2.0 * np.pi * voice.am_rate * t + rng.uniform(0, 6.28)))
    body = body * am
    body += 0.25 * np.std(body) * rng.normal(size=n)  # 气息

    body = _apply_envelope(body, bank, syllable.timbre)

    # 振幅包络：4 ms 起音，尾部 20% 快速收掉（干脆的结尾，也让解码器量到的时长和停顿更稳）
    amp = np.minimum(1.0, t / 0.004)
    tail = int(n * 0.8)
    amp[tail:] *= np.linspace(1.0, 0.0, n - tail) ** 2
    body *= amp
    body /= np.max(np.abs(body)) + 1e-9

    # 真实起音瞬态
    if bank.attacks.size:
        attack = bank.attacks[seed % len(bank.attacks)]
        attack = _apply_envelope(attack, bank, syllable.timbre)
        attack /= np.max(np.abs(attack)) + 1e-9
        m = min(len(attack), n)
        fade = np.linspace(1.0, 0.0, m) ** 2
        body[:m] = body[:m] * (1.0 - 0.4 * fade) + attack[:m] * 0.4 * fade

    # 按 RMS 归一化：深调幅 + 周期加倍让亮音节峰值因数更大，按峰值归一会让它们听起来更轻，
    # 在噪声里先被淹没。整句最后再统一做峰值归一。
    rms = float(np.sqrt(np.mean(body**2))) + 1e-9
    return body / rms * 0.22 * syllable.volume


def _highpass(audio: np.ndarray, cutoff: float) -> np.ndarray:
    spec = np.fft.rfft(audio)
    freqs = np.fft.rfftfreq(len(audio), 1.0 / SR)
    spec *= 1.0 / (1.0 + (cutoff / np.maximum(freqs, 1.0)) ** 4)
    return np.fft.irfft(spec, len(audio))


# 句尾"嘎嘎嘎"三声的音域：一声比一声低一点，像在点头
TAIL_PITCH = (1.08, 1.0, 0.92)


def render_words(
    clauses: list[tuple[list[str], str, list[int]]],
    *,
    voice: str = "adult",
    target: str = "pc",
    tail: bool = True,
    sentence_ends: list[bool] | None = None,
) -> np.ndarray:
    """clauses: [(鸭语词列表, 情绪, 每个词的强调等级)]，返回浮点音频。

    tail=True 时，在 sentence_ends 为 True 的子句后面加句尾装饰"嘎嘎嘎"（默认每个子句都加）。
    """
    if target not in TARGETS:
        raise ValueError(f"未知输出目标：{target}（可选：{', '.join(TARGETS)}）")
    preset = get_voice(voice)
    bank = load_bank()
    ends = sentence_ends if sentence_ends is not None else [True] * len(clauses)
    pieces: list[np.ndarray] = []
    seed = 7

    def say(word: str, emotion: str, emphasis: int, pitches: tuple[float, ...] = ()) -> None:
        nonlocal seed
        syllables = parse_word(word)
        for syl_index, syllable in enumerate(syllables):
            adjusted = adjust(syllable, preset, emotion, emphasis=emphasis)
            if pitches:
                adjusted = replace(adjusted, pitch=adjusted.pitch * pitches[syl_index])
            pieces.append(synth_syllable(adjusted, preset, seed=seed, bank=bank))
            seed += 13
            if syl_index != len(syllables) - 1:
                pieces.append(np.zeros(int(SR * GAP_SYLLABLE / adjusted.tempo)))

    for clause_index, (words, emotion, emphasis) in enumerate(clauses):
        for word_index, word in enumerate(words):
            say(word, emotion, emphasis[word_index])
            if word_index != len(words) - 1:
                pieces.append(np.zeros(int(SR * GAP_WORD)))
        if tail and words and ends[clause_index]:
            pieces.append(np.zeros(int(SR * GAP_WORD)))
            say(TAIL_WORD, emotion, 0, TAIL_PITCH)
        if clause_index != len(clauses) - 1:
            pieces.append(np.zeros(int(SR * GAP_CLAUSE)))
    if not pieces:
        raise ValueError("没有可合成的鸭语音节。")

    lead = np.zeros(int(SR * 0.05))
    audio = np.concatenate([lead, *pieces, np.zeros(int(SR * 0.15))])
    if target == "robot":
        audio = _highpass(audio, 300.0)
    peak = float(np.max(np.abs(audio))) or 1.0
    return audio / peak * 0.89  # -1 dBFS


def write_wav(audio: np.ndarray, path: Path, sr: int = SR) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())
    return path


def out_dir() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    if (project_root / "pyproject.toml").exists():
        directory = project_root / "out"
    else:
        directory = Path.cwd() / "out"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _default_out_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    return out_dir() / f"duck-{stamp}.wav"


def render_result(
    result: TranslationResult,
    *,
    voice: str = "adult",
    emotion: str | None = None,
    out_path: Path | None = None,
    target: str = "pc",
    tail: bool = True,
) -> Path:
    clauses = []
    ends = []
    for clause in result.clauses:
        words: list[str] = []
        emphasis: list[int] = []
        for token in clause.tokens:
            for part in token.text.split():
                words.append(part)
                emphasis.append(token.emphasis)
        if words:
            clauses.append((words, emotion or clause.emotion, emphasis))
            ends.append(clause.punctuation not in {",", "，"})
    if ends:
        ends[-1] = True
    audio = render_words(clauses, voice=voice, target=target, tail=tail, sentence_ends=ends)
    return write_wav(audio, Path(out_path or _default_out_path()))


def render_duck(
    duck: str,
    *,
    voice: str = "adult",
    emotion: str = "neutral",
    out_path: Path | None = None,
    target: str = "pc",
    tail: bool = True,
) -> Path:
    """直接合成一段鸭语文本（不经过翻译）。"""
    from .reverse import _split_clauses

    clauses = []
    ends = []
    for body, punct in _split_clauses(duck.lower()):
        words = [w for w in body.split() if w != TAIL_WORD]
        for word in words:
            parse_word(word)
        if not words:
            continue
        clause_emotion = emotion
        if emotion == "neutral" and punct in {"?", "？"}:
            clause_emotion = "question"
        clauses.append((words, clause_emotion, [0] * len(words)))
        ends.append(punct not in {",", "，"})
    if ends:
        ends[-1] = True
    audio = render_words(clauses, voice=voice, target=target, tail=tail, sentence_ends=ends)
    return write_wav(audio, Path(out_path or _default_out_path()))


def render_text(
    text: str,
    *,
    voice: str = "adult",
    emotion: str | None = None,
    out_path: Path | None = None,
    strict: bool = False,
    target: str = "pc",
    tail: bool = True,
) -> tuple[TranslationResult, Path]:
    from .translator import translate

    result = translate(text, strict=strict)
    path = render_result(result, voice=voice, emotion=emotion, out_path=out_path, target=target,
                         tail=tail)
    return result, path
