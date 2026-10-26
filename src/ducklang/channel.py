"""模拟"机器人小喇叭 -> 房间 -> 麦克风"信道，用于解码器的阶段 B 测试。"""

from __future__ import annotations

import numpy as np


def _fft_filter(audio: np.ndarray, sr: int, response) -> np.ndarray:
    n_fft = 1 << int(np.ceil(np.log2(len(audio) + 1)))
    spec = np.fft.rfft(audio, n_fft)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    return np.fft.irfft(spec * response(np.maximum(freqs, 1.0)), n_fft)[: len(audio)]


def speaker(audio: np.ndarray, sr: int) -> np.ndarray:
    """小喇叭：300 Hz 以下衰减，7 kHz 以上滚降，3 kHz 附近有一点峰。"""

    def response(f):
        hp = 1.0 / (1.0 + (300.0 / f) ** 4)
        lp = 1.0 / (1.0 + (f / 7000.0) ** 4)
        bump = 1.0 + 0.4 * np.exp(-0.5 * ((f - 3000.0) / 700.0) ** 2)
        return hp * lp * bump

    return _fft_filter(audio, sr, response)


def reverb(audio: np.ndarray, sr: int, rng: np.random.Generator,
           rt60: float = 0.2, wet: float = 0.25) -> np.ndarray:
    n = int(sr * rt60 * 1.2)
    t = np.arange(n) / sr
    ir = rng.normal(size=n) * 10 ** (-3.0 * t / rt60)
    ir[: int(sr * 0.003)] = 0.0  # 早期反射前的空隙
    ir /= np.sqrt(np.sum(ir**2)) + 1e-9
    n_fft = 1 << int(np.ceil(np.log2(len(audio) + n)))
    tail = np.fft.irfft(np.fft.rfft(audio, n_fft) * np.fft.rfft(ir, n_fft), n_fft)[: len(audio)]
    return (1.0 - wet) * audio + wet * tail


def add_noise(audio: np.ndarray, rng: np.random.Generator, snr_db: float) -> np.ndarray:
    active = np.abs(audio) > 0.05 * np.max(np.abs(audio))
    signal_rms = np.sqrt(np.mean(audio[active] ** 2)) if active.any() else 1e-3
    white = rng.normal(size=len(audio))
    pink = np.zeros_like(white)
    acc = 0.0
    for i, w in enumerate(white):  # 简单的粉红噪声
        acc = 0.98 * acc + w
        pink[i] = acc
    pink /= np.sqrt(np.mean(pink**2)) + 1e-9
    noise = 0.5 * pink + 0.5 * white
    noise /= np.sqrt(np.mean(noise**2)) + 1e-9
    return audio + noise * signal_rms * 10 ** (-snr_db / 20.0)


def simulate(audio: np.ndarray, sr: int, *, seed: int = 0, snr_db: float = 15.0,
             rt60: float = 0.2, wet: float = 0.25) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = speaker(audio, sr)
    out = reverb(out, sr, rng, rt60=rt60, wet=wet)
    out = add_noise(out, rng, snr_db)
    out *= rng.uniform(0.4, 1.0) / (np.max(np.abs(out)) + 1e-9)
    return out
