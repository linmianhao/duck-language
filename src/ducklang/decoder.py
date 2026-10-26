"""声音 -> 鸭语 -> 中文。纯 DSP，不需要机器学习：编码规则是我们自己定的。

流程：带通 -> 能量检测 -> 按静音长度切成 音节 / 词 / 子句
      -> 每个音节测 时长、首尾基频比、频谱重心 -> 12 类音节
      -> 词典纠错（声学距离 1 以内且唯一）-> 鸭语文本 -> 反向翻译
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .lexicon import Lexicon, Phrasebook
from .phonology import Syllable, word_from_syllables
from .reverse import ReverseResult, reverse

# 判定阈值（与 synth.py 的参数配套）
LONG_THRESHOLD_S = 0.20  # 短 ≈ 0.10–0.16 s，长 ≈ 0.25–0.38 s（噪声会吃掉尾巴）
CONTOUR_THRESHOLD_ST = 2.5  # 降 / 升 ≈ ±6 个半音，平 ≈ 0
CENTROID_THRESHOLD_HZ = 1550.0  # 暗 ≈ 1.1–1.35 kHz，亮 ≈ 1.8–2.1 kHz（几何中点）
WORD_GAP_S = 0.14  # 词内 ≈ 0.05–0.10 s，词间 ≈ 0.19–0.22 s
CLAUSE_GAP_S = 0.36  # 子句间 ≈ 0.50 s
F0_RANGE = (90.0, 800.0)


@dataclass
class DecodedSyllable:
    syllable: Syllable
    start: float
    duration: float
    semitones: float
    centroid: float
    confidence: float


@dataclass
class DecodeResult:
    duck: str
    words: list[str]
    syllables: list[DecodedSyllable]
    confidence: float
    warnings: list[str] = field(default_factory=list)
    translation: ReverseResult | None = None

    @property
    def zh(self) -> str:
        return self.translation.zh if self.translation else ""

    def to_dict(self) -> dict:
        return {
            "duck": self.duck,
            "zh": self.zh,
            "confidence": round(self.confidence, 3),
            "warnings": self.warnings,
            "syllables": [
                {
                    "text": s.syllable.text,
                    "start": round(s.start, 3),
                    "duration": round(s.duration, 3),
                    "semitones": round(s.semitones, 2),
                    "centroid": round(s.centroid),
                    "confidence": round(s.confidence, 3),
                }
                for s in self.syllables
            ],
        }


def read_wav(path: Path | str) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        sr = wav.getframerate()
        width = wav.getsampwidth()
        channels = wav.getnchannels()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("只支持 16-bit PCM WAV")
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, sr


def _bandpass(x: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1.0 / sr)
    spec[(freqs < lo) | (freqs > hi)] = 0.0
    return np.fft.irfft(spec, len(x))


def _segments(x: np.ndarray, sr: int) -> list[tuple[int, int]]:
    hop, win = int(sr * 0.0025), int(sr * 0.010)
    if len(x) <= win:
        return []
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop]
    db = 10 * np.log10(np.mean(frames**2, axis=1) + 1e-12)
    # 20 ms 平滑：抹掉"嘎"本身的深调幅凹陷，免得一声被切成两段
    smooth = int(0.020 * sr / hop)
    db = np.convolve(db, np.ones(smooth) / smooth, mode="same")
    floor, peak = np.percentile(db, 10), np.max(db)
    high = max(floor + 12.0, peak - 20.0)
    low = high - 4.0  # 迟滞，避免在阈值附近抖动
    segs: list[tuple[int, int]] = []
    start = None
    for i, level in enumerate(db):
        if start is None and level > high:
            start = i
        elif start is not None and level < low:
            segs.append((start, i))
            start = None
    if start is not None:
        segs.append((start, len(db)))
    # 先合并 < 20 ms 的缝，再在段内按音色突变切开（混响会填满音节间的静音）
    merged: list[tuple[int, int]] = []
    for s, e in segs:
        if merged and (s - merged[-1][1]) * hop < sr * 0.020:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    spec = np.abs(np.fft.rfft(frames * np.hanning(win), axis=1)) ** 2
    freqs = np.fft.rfftfreq(win, 1.0 / sr)
    band = (freqs > 300) & (freqs < 6000)
    centroid = (spec[:, band] @ freqs[band]) / (spec[:, band].sum(axis=1) + 1e-12)
    pieces = [p for seg in merged for p in _split_at_timbre(centroid, *seg, hop, sr)]
    return [(s * hop, e * hop + win) for s, e in pieces if (e - s) * hop >= sr * 0.040]


def _split_at_timbre(
    centroid: np.ndarray, start: int, end: int, hop: int, sr: int
) -> list[tuple[int, int]]:
    """段内前后两部分分别落在亮 / 暗两侧时切开（例如 wo+ko 被混响粘在一起）。"""
    min_len = int(0.06 * sr / hop)
    if end - start <= 2 * min_len:
        return [(start, end)]
    log_c = np.log2(np.maximum(centroid[start:end], 1.0) / CENTROID_THRESHOLD_HZ)
    best_k, best_gap = None, 0.0
    for k in range(min_len, end - start - min_len):
        left, right = np.median(log_c[:k]), np.median(log_c[k:])
        if left * right < 0 and min(abs(left), abs(right)) > 0.2 and abs(left - right) > best_gap:
            best_k, best_gap = k, abs(left - right)
    if best_k is None:
        return [(start, end)]
    cut = start + best_k
    return (_split_at_timbre(centroid, start, cut, hop, sr)
            + _split_at_timbre(centroid, cut, end, hop, sr))


def _yin_f0(frame: np.ndarray, sr: int) -> float | None:
    n = len(frame)
    lag_min, lag_max = int(sr / F0_RANGE[1]), int(sr / F0_RANGE[0])
    if n < 2 * lag_max:
        return None
    frame = frame - frame.mean()
    w = n - lag_max
    # r(tau) = sum_{j<w} x_j x_{j+tau}
    acf = np.fft.irfft(np.conj(np.fft.rfft(frame[:w], 2 * n)) * np.fft.rfft(frame, 2 * n))
    energy = np.cumsum(frame**2)
    # 差分函数 d(tau) = e(0..w) + e(tau..tau+w) - 2 r(tau)
    e0 = energy[w - 1]
    taus = np.arange(lag_max + 1)
    e_tau = energy[taus + w - 1] - np.concatenate([[0.0], energy[taus[1:] - 1]])
    d = e0 + e_tau - 2 * acf[: lag_max + 1]
    d[0] = 0.0
    cmnd = np.ones_like(d)
    cmnd[1:] = d[1:] * np.arange(1, len(d)) / (np.cumsum(d[1:]) + 1e-12)
    search = cmnd[lag_min:]
    below = np.where(search < 0.2)[0]
    if below.size:
        i = below[0]
        while i + 1 < len(search) and search[i + 1] < search[i]:
            i += 1
    else:
        i = int(np.argmin(search))
        if search[i] > 0.6:
            return None
    lag = i + lag_min
    if 1 <= lag < len(cmnd) - 1:  # 抛物线插值
        a, b, c = cmnd[lag - 1], cmnd[lag], cmnd[lag + 1]
        denom = a - 2 * b + c
        if abs(denom) > 1e-12:
            lag = lag + 0.5 * (a - c) / denom
    return sr / lag


def _contour_semitones(seg: np.ndarray, sr: int) -> float:
    frame, hop = int(sr * 0.025), int(sr * 0.005)
    f0s = []
    for i in range(0, len(seg) - frame, hop):
        f0s.append(_yin_f0(seg[i:i + frame], sr))
    voiced = np.array([f for f in f0s if f is not None])
    if len(voiced) < 4:
        return 0.0
    times = np.array([i * hop for i, f in enumerate(f0s) if f is not None], dtype=float) / sr
    # 八度折叠：鸭叫的周期加倍会让 YIN 在 f0 和 f0/2 之间跳。按"音级"取圆周平均作参考，
    # 把每帧折叠到参考 ±6 个半音以内（音节内走势只有 ±4 个半音左右，不会被折坏）
    st = 12 * np.log2(voiced)
    angle = 2 * np.pi * st / 12
    ref = 12 * np.angle(np.mean(np.exp(1j * angle))) / (2 * np.pi)
    d = st - ref
    st = ref + d - 12 * np.round(d / 12)
    # Theil-Sen 斜率：对首尾被混响拖尾污染的帧不敏感
    i, j = np.triu_indices(len(st), k=1)
    dt = times[j] - times[i]
    keep = dt > 0
    slope = np.median((st[j][keep] - st[i][keep]) / dt[keep])
    return float(slope * (len(seg) / sr))


def _centroid(seg: np.ndarray, sr: int) -> float:
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    freqs = np.fft.rfftfreq(len(seg), 1.0 / sr)
    band = (freqs > 300) & (freqs < 6000)
    return float(np.sum(freqs[band] * spec[band]) / (np.sum(spec[band]) + 1e-12))


def _classify(duration: float, semitones: float, centroid: float) -> tuple[Syllable, float]:
    timbre = "k" if centroid >= CENTROID_THRESHOLD_HZ else "w"
    if semitones <= -CONTOUR_THRESHOLD_ST:
        contour = "a"
    elif semitones >= CONTOUR_THRESHOLD_ST:
        contour = "i"
    else:
        contour = "o"
    long = duration >= LONG_THRESHOLD_S
    # 置信度：每个特征离阈值多远（0..1），取最小
    c_timbre = min(1.0, abs(np.log2(centroid / CENTROID_THRESHOLD_HZ)) / 0.35)
    c_contour = min(1.0, abs(abs(semitones) - CONTOUR_THRESHOLD_ST) / 2.5)
    c_long = min(1.0, abs(np.log(duration / LONG_THRESHOLD_S)) / 0.35)
    return Syllable(timbre, contour, long), float(min(c_timbre, c_contour, c_long))


def decode_audio(
    audio: np.ndarray,
    sr: int,
    *,
    lexicon: Lexicon | None = None,
    phrasebook: Phrasebook | None = None,
    translate: bool = True,
) -> DecodeResult:
    lexicon = lexicon or Lexicon.load()
    warnings: list[str] = []
    band = _bandpass(audio, sr, 500.0, 5000.0)
    for_pitch = _bandpass(audio, sr, 80.0, 6000.0)
    segs = _segments(band, sr)
    if not segs:
        return DecodeResult("", [], [], 0.0, ["没有检测到鸭叫"])

    decoded: list[DecodedSyllable] = []
    for start, end in segs:
        duration = (end - start) / sr
        semitones = _contour_semitones(for_pitch[start:end], sr)
        centroid = _centroid(band[start:end], sr)
        syllable, confidence = _classify(duration, semitones, centroid)
        decoded.append(DecodedSyllable(syllable, start / sr, duration, semitones, centroid,
                                       confidence))

    # 按静音长度切成 子句 / 词
    clauses: list[list[list[DecodedSyllable]]] = [[[decoded[0]]]]
    for prev, cur, (_, prev_end), (cur_start, _) in zip(
        decoded, decoded[1:], segs, segs[1:], strict=False
    ):
        gap = (cur_start - prev_end) / sr
        if gap >= CLAUSE_GAP_S:
            clauses.append([[cur]])
        elif gap >= WORD_GAP_S:
            clauses[-1].append([cur])
        else:
            clauses[-1][-1].append(cur)

    words_out: list[str] = []
    clause_texts: list[str] = []
    for clause in clauses:
        texts = []
        for group in clause:
            raw = word_from_syllables([d.syllable for d in group])
            word = raw
            if lexicon.lookup_duck(raw) is None:
                near = lexicon.nearest(raw)
                if near is not None:
                    warnings.append(f"纠错：{raw} -> {near.duck}")
                    word = near.duck
                else:
                    warnings.append(f"无法识别的词：{raw}")
            texts.append(word)
            words_out.append(word)
        end = "?" if texts and texts[-1] == "ki" else "。"
        clause_texts.append(" ".join(texts) + end)

    duck = " ".join(clause_texts)
    confidence = float(np.mean([d.confidence for d in decoded]))
    result = DecodeResult(duck, words_out, decoded, confidence, warnings)
    if translate:
        result.translation = reverse(duck, lexicon=lexicon, phrasebook=phrasebook)
    return result


def decode(path: Path | str, **kwargs) -> DecodeResult:
    audio, sr = read_wav(path)
    return decode_audio(audio, sr, **kwargs)
