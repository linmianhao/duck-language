import wave

import numpy as np
import pytest

from ducklang import speak
from ducklang.phonology import ALL_SYLLABLES
from ducklang.prosody import EMOTIONS, VOICES, adjust, get_voice
from ducklang.synth import SR, load_bank, render_duck, render_result, synth_syllable
from ducklang.translator import translate


def _read_wav(path):
    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        data = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    return rate, data


def _band_share(audio, lo, hi):
    spec = np.abs(np.fft.rfft(audio * np.hanning(len(audio)))) ** 2
    freqs = np.fft.rfftfreq(len(audio), 1.0 / SR)
    return spec[(freqs >= lo) & (freqs < hi)].sum() / spec.sum()


def _centroid(audio):
    spec = np.abs(np.fft.rfft(audio * np.hanning(len(audio)))) ** 2
    freqs = np.fft.rfftfreq(len(audio), 1.0 / SR)
    return float((freqs * spec).sum() / spec.sum())


def test_voice_bank_comes_from_samples():
    assert load_bank().from_samples


def test_render_result_writes_48k_wav_without_clipping(tmp_path):
    path = render_result(translate("你好吗？"), voice="duckling", out_path=tmp_path / "hi.wav")
    rate, data = _read_wav(path)
    assert rate == 48_000
    assert len(data) / rate > 0.5
    peak = np.max(np.abs(data)) / 32768
    assert 0.5 < peak <= 10 ** (-1 / 20) + 1e-3  # 不超过 -1 dBFS


@pytest.mark.parametrize("syllable", ALL_SYLLABLES, ids=lambda s: s.text)
def test_syllables_sound_like_ducks(syllable):
    """标定目标（真实鸭叫 1–3 kHz 能量占 59–93%）：亮音色 ≥ 50%，暗音色 ≥ 40%。"""
    voice = get_voice("adult")
    audio = synth_syllable(adjust(syllable, voice, "neutral"), voice)
    share = _band_share(audio, 1000, 3000)
    assert share >= (0.5 if syllable.timbre == "k" else 0.4)
    assert np.all(np.isfinite(audio))


def test_bright_and_dark_are_far_apart():
    voice = get_voice("adult")
    bright = [_centroid(synth_syllable(adjust(s, voice, "neutral"), voice))
              for s in ALL_SYLLABLES if s.timbre == "k"]
    dark = [_centroid(synth_syllable(adjust(s, voice, "neutral"), voice))
            for s in ALL_SYLLABLES if s.timbre == "w"]
    assert min(bright) > 1.3 * max(dark)


def test_long_syllables_are_much_longer():
    for name in VOICES:
        voice = get_voice(name)
        for emotion in EMOTIONS:
            durations = {
                s.long: len(synth_syllable(adjust(s, voice, emotion), voice)) / SR
                for s in ALL_SYLLABLES if s.contour == "o" and s.timbre == "k"
            }
            assert durations[True] >= 2.2 * durations[False]


def test_render_duck_and_robot_target(tmp_path):
    path = render_duck("kaakaa!", target="robot", out_path=tmp_path / "danger.wav")
    _, data = _read_wav(path)
    audio = data / 32768
    assert _band_share(audio, 0, 250) < 0.02


def test_invalid_target_rejected(tmp_path):
    with pytest.raises(ValueError):
        render_duck("ka", target="tv", out_path=tmp_path / "x.wav")


def test_speak_without_play(tmp_path):
    speech = speak("我饿了", play=False, out_path=tmp_path / "hungry.wav")
    assert speech.played is False
    assert speech.path.exists()
    assert speech.result.duck == "ka wakaa kii。"
