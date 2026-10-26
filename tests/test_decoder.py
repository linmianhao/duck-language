import itertools

import numpy as np
import pytest

from ducklang.channel import simulate
from ducklang.decoder import decode, decode_audio, read_wav
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


def test_tail_is_audible_but_stripped(tmp_path):
    """句尾"嘎嘎嘎"让声音更长，但解码结果和原文一致。"""
    with_tail = render_duck("ka wakaa kii。 wa wi ki?", out_path=tmp_path / "t.wav")
    without = render_duck("ka wakaa kii。 wa wi ki?", tail=False, out_path=tmp_path / "n.wav")
    a, _ = read_wav(with_tail)
    b, _ = read_wav(without)
    assert len(a) - len(b) > 2 * 0.5 * SR  # 两句，每句多出约 0.8 秒
    for path in (with_tail, without):
        decoded = decode(path)
        assert decoded.duck == "ka wakaa kii。 wa wi ki?"
        assert len(decoded.syllables) == 7


def test_tail_only_after_sentences_not_commas(tmp_path):
    from ducklang.synth import render_result
    from ducklang.translator import translate

    result = translate("我饿了，我们去水边吧")
    with_tail, _ = read_wav(render_result(result, out_path=tmp_path / "t.wav"))
    without, _ = read_wav(render_result(result, tail=False, out_path=tmp_path / "n.wav"))
    extra = (len(with_tail) - len(without)) / SR
    assert 0.5 < extra < 1.2  # 只在整句末尾加一次，逗号后面不加
    assert decode(tmp_path / "t.wav").words == result.words


def test_damaged_tail_is_still_stripped():
    """噪声吃掉一声时剩下的 kaka 在子句末尾也当作装饰。"""
    audio = render_words([(["ka", "wakaa", "kii", "kaka"], "neutral", [0, 0, 0, 0])], tail=False)
    assert decode_audio(audio, SR, translate=False).words == ["ka", "wakaa", "kii"]


def test_silence_does_not_crash():
    decoded = decode_audio(np.zeros(SR), SR)
    assert decoded.duck == ""
    assert decoded.warnings
