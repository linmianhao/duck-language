import wave

import numpy as np

from ducklang import speak
from ducklang.synth import render_result
from ducklang.translator import translate


def _read_wav(path):
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        data = np.frombuffer(wav.readframes(frames), dtype=np.int16)
    return rate, frames, data


def test_render_result_writes_valid_wav(tmp_path):
    result = translate("你好吗？")
    path = render_result(result, voice="duckling", out_path=tmp_path / "hello.wav")

    assert path.exists()
    rate, frames, data = _read_wav(path)
    assert rate == 44_100
    assert frames / rate > 0.5
    assert data.size > 0
    assert np.max(np.abs(data)) > 0
    assert np.max(np.abs(data)) < 32_767
    assert np.all(np.isfinite(data))


def test_render_alarm_voice(tmp_path):
    result = translate("危险！")
    path = render_result(result, voice="angry", out_path=tmp_path / "danger.wav")
    assert path.exists()
    _, frames, data = _read_wav(path)
    assert frames > 0
    assert np.max(np.abs(data)) <= 32_767


def test_speak_without_play(tmp_path):
    speech = speak("我饿了", play=False, out_path=tmp_path / "hungry.wav")
    assert speech.played is False
    assert speech.path.exists()
    assert speech.result.duck == "ma mam ʔi。"


def test_render_unknown_loanword(tmp_path):
    result = translate("我喝咖啡")
    path = render_result(result, out_path=tmp_path / "coffee.wav")
    assert path.exists()
