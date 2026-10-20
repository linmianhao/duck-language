from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ir import TranslationResult
from .player import play_wav
from .synth import render_result
from .translator import translate


@dataclass
class Speech:
    result: TranslationResult
    path: Path
    played: bool


def speak(
    text: str,
    *,
    voice: str = "adult",
    emotion: str | None = None,
    out_path: Path | None = None,
    play: bool = True,
    strict: bool = False,
) -> Speech:
    result = translate(text, strict=strict)
    path = render_result(result, voice=voice, emotion=emotion, out_path=out_path)
    played = play_wav(path) if play else False
    return Speech(result=result, path=path, played=played)
