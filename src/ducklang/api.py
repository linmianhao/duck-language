from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .decoder import DecodeResult, decode
from .ir import TranslationResult
from .player import play_wav
from .reverse import ReverseResult, reverse
from .synth import render_duck, render_result
from .translator import translate


@dataclass
class Speech:
    result: TranslationResult
    path: Path
    played: bool


def render(
    result: TranslationResult | str,
    *,
    voice: str = "adult",
    emotion: str | None = None,
    out_path: Path | None = None,
    target: str = "pc",
) -> Path:
    """合成 WAV：传 TranslationResult 或一段鸭语文本。"""
    if isinstance(result, str):
        return render_duck(result, voice=voice, emotion=emotion or "neutral",
                           out_path=out_path, target=target)
    return render_result(result, voice=voice, emotion=emotion, out_path=out_path, target=target)


def speak(
    text: str,
    *,
    voice: str = "adult",
    emotion: str | None = None,
    out_path: Path | None = None,
    play: bool = True,
    strict: bool = False,
    target: str = "pc",
) -> Speech:
    result = translate(text, strict=strict)
    path = render_result(result, voice=voice, emotion=emotion, out_path=out_path, target=target)
    played = play_wav(path) if play else False
    return Speech(result=result, path=path, played=played)


__all__ = [
    "DecodeResult", "ReverseResult", "Speech", "decode", "render", "reverse", "speak", "translate",
]
