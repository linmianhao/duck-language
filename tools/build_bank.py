"""从真实鸭叫录音构建合成用的音色库 data/voice_bank.npz。

    uv run --group tools python tools/build_bank.py samples/raw/*.mp3

做三件事：
1. 能量检测切出每一声鸭叫；
2. 用倒谱平滑提取每声叫的频谱包络，取平均作为"亮"音色，再整体下移得到"暗"音色；
3. 截取每声叫开头约 15 ms 的起音瞬态，供合成时交叉淡入。

不直接对录音变调拼接：变调会连带移动共振峰，从而改变亮/暗分类，影响解码。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

SR = 48_000
GRID = np.linspace(0.0, SR / 2, 513)  # 包络频率网格
DARK_WARP = 0.62  # 暗音色 = 亮音色频率轴乘以这个系数
ATTACK_MS = 15


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf
    except ImportError:
        sf = None
    if sf is not None:
        data, sr = sf.read(str(path), dtype="float64")
    else:
        import wave

        with wave.open(str(path), "rb") as wav:
            sr = wav.getframerate()
            raw = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
            data = raw.reshape(-1, wav.getnchannels()).astype(np.float64) / 32768.0
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, sr


def resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return x
    n_to = round(len(x) * sr_to / sr_from)
    spec = np.fft.rfft(x)
    out = np.zeros(n_to // 2 + 1, dtype=complex)
    keep = min(len(spec), len(out))
    out[:keep] = spec[:keep]
    return np.fft.irfft(out, n_to) * (n_to / len(x))


def find_calls(x: np.ndarray, sr: int) -> list[tuple[int, int]]:
    hop, win = int(sr * 0.005), int(sr * 0.020)
    rms = np.array([np.sqrt(np.mean(x[i:i + win] ** 2)) for i in range(0, len(x) - win, hop)])
    db = 20 * np.log10(rms + 1e-9)
    active = db > np.percentile(db, 95) - 18
    calls: list[tuple[int, int]] = []
    start = None
    for i, on in enumerate(np.append(active, False)):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= 12:  # >= 60 ms
                if calls and start * hop - calls[-1][1] < int(sr * 0.025):
                    calls[-1] = (calls[-1][0], i * hop + win)
                else:
                    calls.append((start * hop, i * hop + win))
            start = None
    return calls


def cepstral_envelope(seg: np.ndarray, sr: int) -> np.ndarray:
    n = 2048
    frame, hop = int(sr * 0.030), int(sr * 0.010)
    lifter = int(sr * 0.0022)  # 去掉 > 2.2 ms 的倒谱，也就是基频谐波结构
    envs = []
    for i in range(0, max(1, len(seg) - frame), hop):
        chunk = seg[i:i + frame]
        if len(chunk) < frame:
            break
        if np.sqrt(np.mean(chunk ** 2)) < 1e-4:
            continue
        mag = np.abs(np.fft.rfft(chunk * np.hanning(frame), n)) + 1e-9
        cep = np.fft.irfft(np.log(mag), n)
        cep[lifter:n - lifter] = 0.0
        envs.append(np.exp(np.fft.rfft(cep, n).real))
    env = np.mean(envs, axis=0)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    out = np.interp(GRID, freqs, env, right=env[-1] * 0.1)
    return out / out.max()


def warp(env: np.ndarray, factor: float) -> np.ndarray:
    warped = np.interp(GRID / factor, GRID, env, right=env[-1])
    tilt = 1.0 / (1.0 + (GRID / 4000.0) ** 2)  # 暗音色再压一点高频
    warped *= tilt
    return warped / warped.max()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/voice_bank.npz"))
    args = parser.parse_args(argv)

    envelopes, attacks, sources = [], [], []
    for path in args.inputs:
        x, sr = load_audio(path)
        x = resample(x, sr, SR)
        calls = find_calls(x, SR)
        print(f"{path.name}: {len(calls)} 声")
        for start, end in calls:
            seg = x[start:end]
            envelopes.append(cepstral_envelope(seg, SR))
            n_att = int(SR * ATTACK_MS / 1000)
            onset = int(np.argmax(np.abs(seg[: int(SR * 0.05)]) > 0.2 * np.max(np.abs(seg))))
            att = seg[max(0, onset - 48): max(0, onset - 48) + n_att]
            if len(att) == n_att:
                attacks.append(att / (np.max(np.abs(att)) + 1e-9))
        sources.append(path.name)

    if not envelopes:
        print("没有找到鸭叫", file=sys.stderr)
        return 1
    bright = np.mean(envelopes, axis=0)
    bright /= bright.max()
    dark = warp(bright, DARK_WARP)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        grid=GRID.astype(np.float32),
        bright=bright.astype(np.float32),
        dark=dark.astype(np.float32),
        attacks=np.array(attacks, dtype=np.float32),
        sources=np.array(sources),
    )
    peak_b = GRID[np.argmax(bright)]
    peak_d = GRID[np.argmax(dark)]
    print(f"写入 {args.out}：{len(envelopes)} 个包络，{len(attacks)} 个起音；"
          f"亮峰 {peak_b:.0f} Hz，暗峰 {peak_d:.0f} Hz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
