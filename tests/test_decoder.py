import itertools

import numpy as np
import pytest

from ducklang.channel import simulate
from ducklang.decoder import decode, decode_audio
from ducklang.phonology import ALL_SYLLABLES
from ducklang.prosody import VOICES
from ducklang.synth import SR, render_duck, render_words
from ducklang.translator import translate

SENTENCES = ["我饿了，我们去水边吧", "你吃了吗？", "危险！", "谁想吃虫子？", "我和你去玩"]


def _render(text, voice, emotion):
    result = translate(text)
    clauses = [
        (clause.words, emotion, [t.emphasis for t in clause.tokens for _ in t.text.split()])
        for clause in result.clauses
    ]
    return result, render_words(clauses, voice=voice)


def test_every_syllable_decodes():
    words = [s.text for s in ALL_SYLLABLES]
    audio = render_words([(words, "neutral", [0] * len(words))])
    decoded = decode_audio(audio, SR, translate=False)
    assert [s.syllable.text for s in decoded.syllables] == words


@pytest.mark.parametrize(
    ("voice", "emotion"), list(itertools.product(VOICES, ["neutral", "alarm", "soft"]))
)
def test_stage_a_clean(voice, emotion):
    """阶段 A：合成 WAV 直接解码，音节准确率 100%。"""
    for text in SENTENCES:
        result, audio = _render(text, voice, emotion)
        decoded = decode_audio(audio, SR, translate=False)
        assert decoded.words == result.words, text


def test_stage_b_simulated_channel():
    """阶段 B：小喇叭 + 混响 + 噪声，音节准确率 ≥ 98%，整句准确率 ≥ 90%。"""
    total = errors = wrong = n = 0
    for n, (text, voice) in enumerate(itertools.product(SENTENCES, VOICES), start=1):
        result, audio = _render(text, voice, "neutral")
        noisy = simulate(audio, SR, seed=n, snr_db=12.0, rt60=0.3, wet=0.3)
        decoded = decode_audio(noisy, SR, translate=False)
        want = "".join(result.words)
        got = "".join(decoded.words)
        total += len(want)
        errors += sum(a != b for a, b in zip(want, got)) + abs(len(want) - len(got))
        wrong += decoded.words != result.words
    assert errors / total <= 0.02
    assert wrong / n <= 0.10


def test_decode_file_and_translate(tmp_path):
    path = render_duck("wa waka koo ki?", out_path=tmp_path / "q.wav")
    decoded = decode(path)
    assert decoded.duck == "wa waka koo ki?"
    assert decoded.zh == "你吃了吗？"
    assert decoded.confidence > 0.5


def test_silence_does_not_crash():
    decoded = decode_audio(np.zeros(SR), SR)
    assert decoded.duck == ""
    assert decoded.warnings
