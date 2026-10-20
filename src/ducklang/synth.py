from __future__ import annotations

import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from .ir import TranslationResult
from .phonology import Syllable, parse_word
from .prosody import Voice, adjust, get_voice

SR = 44_100
FORMANTS = {
    "a": (850.0, 1500.0, 2800.0),
    "e": (550.0, 1900.0, 2700.0),
    "i": (320.0, 2300.0, 3100.0),
    "o": (520.0, 900.0, 2500.0),
    "u": (360.0, 800.0, 2400.0),
}


def _rng(seed: int = 7) -> np.random.Generator:
    return np.random.default_rng(seed)


def _formant_envelope(n: int, vowel: str) -> np.ndarray:
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    f1, f2, f3 = FORMANTS.get(vowel, FORMANTS["a"])
    env = 0.035 + 0.02 / (1.0 + (freqs / 240.0) ** 2)
    for center, bandwidth, gain in ((f1, 130.0, 1.0), (f2, 190.0, 0.55), (f3, 260.0, 0.25)):
        env += gain * np.exp(-0.5 * ((freqs - center) / bandwidth) ** 2)
    return env


def _source(n: int, f0: float, dur: float, rough: float, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / SR
    contour = f0 * (1.0 + 0.13 * np.sin(np.pi * t / max(dur, 1e-6)))
    contour *= 1.0 + 0.022 * np.sin(2.0 * np.pi * 24.0 * t)
    phase = 2.0 * np.pi * np.cumsum(contour) / SR
    source = (
        np.sin(phase)
        + 0.55 * np.sin(2.0 * phase)
        + 0.30 * np.sin(3.0 * phase)
        + 0.14 * np.sin(4.0 * phase)
    )
    source += rough * 0.10 * rng.normal(size=n)
    return source


def _lowpass(signal: np.ndarray, width: int = 17) -> np.ndarray:
    kernel = np.ones(width, dtype=np.float64) / width
    return np.convolve(signal, kernel, mode="same")


def _nasal(dur: float, f0: float, rng: np.random.Generator) -> np.ndarray:
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR
    hum = 0.45 * np.sin(2.0 * np.pi * f0 * 0.55 * t)
    hum += 0.18 * np.sin(2.0 * np.pi * f0 * 1.1 * t)
    hum += 0.05 * rng.normal(size=n)
    hum = _lowpass(hum)
    hum *= np.exp(-t / max(dur * 0.7, 1e-6))
    return hum


def _burst(dur: float, low: bool, rng: np.random.Generator) -> np.ndarray:
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR
    noise = rng.normal(size=n)
    if low:
        noise = _lowpass(noise, 25)
        burst = 0.7 * np.sin(2.0 * np.pi * 105.0 * t) + 0.5 * noise
        return burst * np.exp(-t / 0.010)
    noise = np.diff(noise, prepend=0.0)
    return 0.8 * noise * np.exp(-t / 0.007)


def _consonant_onset(onset: str, rng: np.random.Generator) -> np.ndarray:
    if not onset:
        return np.zeros(0)
    if onset.startswith(("k", "g")):
        return np.concatenate([_burst(0.028, False, rng), np.zeros(int(SR * 0.008))])
    if onset.startswith("t"):
        return np.concatenate([_burst(0.018, False, rng) * 0.75, np.zeros(int(SR * 0.006))])
    if onset.startswith("h"):
        n = int(SR * 0.045)
        t = np.arange(n) / SR
        breath = rng.normal(size=n) * np.exp(-t / 0.022)
        return np.concatenate([_lowpass(breath, 5) * 0.35, np.zeros(int(SR * 0.006))])
    if onset.startswith(("p", "b")):
        return np.concatenate([_burst(0.022, True, rng), np.zeros(int(SR * 0.006))])
    if onset.startswith("m"):
        return _nasal(0.050, 120.0, rng)
    if onset.startswith("n"):
        return _nasal(0.042, 135.0, rng)
    if onset.startswith("ʔ"):
        n = int(SR * 0.018)
        click = np.zeros(n)
        click[0] = 0.7
        return np.concatenate([click, np.zeros(int(SR * 0.012))])
    if onset.startswith("w") or onset.endswith("w"):
        n = int(SR * 0.035)
        t = np.arange(n) / SR
        return 0.16 * np.sin(2.0 * np.pi * 300.0 * t) * np.exp(-t / 0.022)
    return np.zeros(0)


def _coda_tail(coda: str, rng: np.random.Generator) -> np.ndarray:
    if not coda:
        return np.zeros(0)
    if coda in {"k", "g"}:
        return np.concatenate([np.zeros(int(SR * 0.006)), _burst(0.024, False, rng) * 0.8])
    if coda in {"m", "n"}:
        return _nasal(0.060, 115.0 if coda == "m" else 130.0, rng)
    if coda == "ʔ":
        n = int(SR * 0.018)
        click = np.zeros(n)
        click[0] = 0.5
        return np.concatenate([click, np.zeros(int(SR * 0.010))])
    return np.zeros(0)


def _body(
    syllable: Syllable,
    voice: Voice,
    emotion: str,
    final: bool,
    rng: np.random.Generator,
) -> np.ndarray:
    base = 0.135 if syllable.length < 1.25 else 0.180
    dur = base * syllable.length / voice.speed
    n = max(1, int(SR * dur))
    t = np.arange(n) / SR

    f0 = voice.f0 * syllable.pitch
    source = _source(n, f0, dur, voice.rough, rng)

    spectrum = np.fft.rfft(source)
    body = np.fft.irfft(spectrum * _formant_envelope(n, syllable.vowel), n)

    attack = max(1, int(SR * 0.007))
    amp = np.minimum(1.0, t / (attack / SR))
    amp *= np.exp(-1.7 * t / max(dur, 1e-6))
    amp *= 0.84 + 0.16 * np.sin(2.0 * np.pi * 27.0 * t)
    amp *= 1.0 + 0.22 * np.exp(-0.5 * ((t - 0.56 * dur) / (0.13 * dur + 1e-6)) ** 2)
    if final and emotion == "question":
        amp *= 1.0 + 0.25 * (t / max(dur, 1e-6)) ** 2

    body *= amp
    body = np.tanh((1.25 + 2.2 * voice.rough) * body)
    peak = float(np.max(np.abs(body))) or 1.0
    body = body / peak * 0.55 * syllable.volume
    return body


def synth_syllable(
    syllable: Syllable,
    voice: Voice,
    emotion: str = "neutral",
    *,
    final: bool = False,
    seed: int = 7,
) -> np.ndarray:
    rng = _rng(seed)
    onset = _consonant_onset(syllable.onset, rng)
    body = _body(syllable, voice, emotion, final, rng)
    coda = _coda_tail(syllable.coda, rng)
    audio = np.concatenate([part for part in (onset, body, coda) if len(part)])

    fade = max(1, int(SR * 0.004))
    if len(audio) > 2 * fade:
        audio[:fade] *= np.linspace(0.0, 1.0, fade)
        audio[-fade:] *= np.linspace(1.0, 0.0, fade)

    peak = float(np.max(np.abs(audio))) or 1.0
    return audio / peak * min(0.7, 0.55 * syllable.volume)


def write_wav(audio: np.ndarray, path: Path, sr: int = SR) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())
    return path


def _default_out_path() -> Path:
    here = Path(__file__).resolve()
    project_root = here.parents[2]
    if (project_root / "pyproject.toml").exists():
        out_dir = project_root / "out"
    else:
        out_dir = Path.cwd() / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    return out_dir / f"duck-{stamp}.wav"


def render_result(
    result: TranslationResult,
    *,
    voice: str = "adult",
    emotion: str | None = None,
    out_path: Path | None = None,
) -> Path:
    preset = get_voice(voice)
    pieces: list[np.ndarray] = []

    for clause_index, clause in enumerate(result.clauses):
        clause_emotion = emotion or clause.emotion
        syllables: list[tuple[Syllable, int]] = []
        for token in clause.tokens:
            for part in token.text.split():
                try:
                    parsed = parse_word(part)
                except ValueError:
                    continue
                for syllable in parsed:
                    syllables.append((syllable, token.emphasis))

        for index, (syllable, emphasis) in enumerate(syllables):
            adjusted = adjust(
                syllable,
                preset,
                clause_emotion,
                final=index == len(syllables) - 1,
                emphasis=emphasis,
            )
            audio = synth_syllable(
                adjusted,
                preset,
                clause_emotion,
                final=index == len(syllables) - 1,
                seed=7 + clause_index * 31 + index * 7,
            )
            pieces.append(audio)
            if index != len(syllables) - 1:
                gap = 0.020 if clause_emotion != "soft" else 0.035
                pieces.append(np.zeros(int(SR * gap), dtype=np.float64))

        pause = 0.28
        if clause.punctuation == ",":
            pause = 0.15
        elif clause.punctuation in "?？":
            pause = 0.30
        elif clause.punctuation in "!！":
            pause = 0.22
        pieces.append(np.zeros(int(SR * pause), dtype=np.float64))

    if not pieces:
        raise ValueError("没有可合成的鸭语音节。")

    audio = np.concatenate(pieces)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio / peak * 0.9

    fade = max(1, int(SR * 0.008))
    if len(audio) > 2 * fade:
        audio[:fade] *= np.linspace(0.0, 1.0, fade)
        audio[-fade:] *= np.linspace(1.0, 0.0, fade)

    path = out_path or _default_out_path()
    return write_wav(audio, Path(path))


def render_text(
    text: str,
    *,
    voice: str = "adult",
    emotion: str | None = None,
    out_path: Path | None = None,
    strict: bool = False,
) -> tuple[TranslationResult, Path]:
    from .translator import translate

    result = translate(text, strict=strict)
    path = render_result(result, voice=voice, emotion=emotion, out_path=out_path)
    return result, path
