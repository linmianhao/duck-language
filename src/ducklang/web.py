from __future__ import annotations

import argparse
import io
import os
import re
import uuid
import wave
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .decoder import decode_audio
from .prosody import EMOTIONS, VOICES
from .reverse import reverse
from .synth import TARGETS, render_duck, render_result
from .translator import UnknownWordError, translate

STATIC_DIR = Path(__file__).resolve().parent / "static"
AUDIO_RE = re.compile(r"^duck-web-[0-9a-f]{12}\.wav$")
KEEP_AUDIO_FILES = 200
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

VOICE_LABELS = {"duckling": "幼鸭", "adult": "成鸭", "angry": "愤怒鸭", "soft": "温柔鸭"}
EMOTION_LABELS = {
    "neutral": "平静", "question": "疑问", "excited": "兴奋", "alarm": "警报", "soft": "温柔",
}

app = FastAPI(title="嘎语翻译器", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    voice: str = "adult"
    emotion: str | None = None
    strict: bool = False
    target: str = "pc"


class TranslateResponse(BaseModel):
    source: str
    duck: str
    gloss: str
    warnings: list[str]
    audio_url: str
    voice: str
    emotion: str | None = None
    duration: float


class ReverseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    voice: str = "adult"
    emotion: str | None = None
    target: str = "pc"


class ReverseResponse(BaseModel):
    source: str
    zh: str
    gloss: str
    warnings: list[str]
    audio_url: str | None = None
    duration: float = 0.0


class DecodeResponse(BaseModel):
    duck: str
    zh: str
    gloss: str
    confidence: float
    warnings: list[str]
    syllables: list[dict]


def _audio_dir() -> Path:
    override = os.environ.get("DUCKLANG_WEB_AUDIO_DIR")
    if override:
        directory = Path(override)
    else:
        root = Path(__file__).resolve().parents[2]
        directory = root / "out" if (root / "pyproject.toml").exists() else Path.cwd() / "out"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _new_audio_path() -> tuple[str, Path]:
    directory = _audio_dir()
    files = sorted(directory.glob("duck-web-*.wav"), key=lambda p: p.stat().st_mtime)
    for old in files[: max(0, len(files) - KEEP_AUDIO_FILES + 1)]:
        old.unlink(missing_ok=True)
    filename = f"duck-web-{uuid.uuid4().hex[:12]}.wav"
    return filename, directory / filename


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return round(wav.getnframes() / wav.getframerate(), 3)


def _check_options(voice: str, emotion: str | None, target: str) -> None:
    if voice not in VOICES:
        raise HTTPException(status_code=400, detail=f"未知音色：{voice}")
    if emotion is not None and emotion not in EMOTIONS:
        raise HTTPException(status_code=400, detail=f"未知情绪：{emotion}")
    if target not in TARGETS:
        raise HTTPException(status_code=400, detail=f"未知输出目标：{target}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/voices")
def voices() -> dict[str, list[dict[str, object]]]:
    return {
        "voices": [
            {"id": name, "label": VOICE_LABELS.get(name, name), "f0": preset.f0,
             "speed": preset.speed, "rough": preset.rough}
            for name, preset in VOICES.items()
        ],
        "emotions": [{"id": name, "label": EMOTION_LABELS.get(name, name)} for name in EMOTIONS],
        "targets": [{"id": "pc", "label": "电脑"}, {"id": "robot", "label": "机器人喇叭"}],
    }


@app.post("/api/translate", response_model=TranslateResponse)
def api_translate(request: TranslateRequest) -> TranslateResponse:
    _check_options(request.voice, request.emotion, request.target)
    try:
        result = translate(request.text, strict=request.strict)
    except (UnknownWordError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename, path = _new_audio_path()
    render_result(result, voice=request.voice, emotion=request.emotion, out_path=path,
                  target=request.target)
    return TranslateResponse(
        source=result.source,
        duck=result.duck,
        gloss=result.gloss,
        warnings=result.warnings,
        audio_url=f"/api/audio/{filename}",
        voice=request.voice,
        emotion=request.emotion,
        duration=_duration(path),
    )


@app.post("/api/reverse", response_model=ReverseResponse)
def api_reverse(request: ReverseRequest) -> ReverseResponse:
    _check_options(request.voice, request.emotion, request.target)
    try:
        result = reverse(request.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audio_url, duration = None, 0.0
    try:
        filename, path = _new_audio_path()
        render_duck(request.text, voice=request.voice, emotion=request.emotion or "neutral",
                    out_path=path, target=request.target)
        audio_url, duration = f"/api/audio/{filename}", _duration(path)
    except ValueError:
        pass  # 有非法音节时只翻译不发声
    return ReverseResponse(
        source=result.source,
        zh=result.zh,
        gloss=result.gloss,
        warnings=result.warnings,
        audio_url=audio_url,
        duration=duration,
    )


@app.post("/api/decode", response_model=DecodeResponse)
async def api_decode(request: Request) -> DecodeResponse:
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="请上传 WAV 音频")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="音频太大（上限 10 MB）")
    try:
        with wave.open(io.BytesIO(body), "rb") as wav:
            if wav.getsampwidth() != 2:
                raise HTTPException(status_code=400, detail="只支持 16-bit PCM WAV")
            sr = wav.getframerate()
            channels = wav.getnchannels()
            data = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    except (wave.Error, EOFError) as exc:
        raise HTTPException(status_code=400, detail="不是有效的 WAV 文件") from exc
    audio = data.astype(np.float64) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    result = decode_audio(audio, sr)
    payload = result.to_dict()
    return DecodeResponse(
        duck=result.duck,
        zh=result.zh,
        gloss=result.translation.gloss if result.translation else "",
        confidence=payload["confidence"],
        warnings=result.warnings + (result.translation.warnings if result.translation else []),
        syllables=payload["syllables"],
    )


@app.get("/api/audio/{filename}")
def audio(filename: str) -> FileResponse:
    if not AUDIO_RE.fullmatch(filename):
        raise HTTPException(status_code=404, detail="音频不存在")
    path = _audio_dir() / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="音频不存在")
    return FileResponse(path, media_type="audio/wav",
                        headers={"Cache-Control": "public, max-age=3600"})


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="启动嘎语翻译器 Web 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("ducklang.web:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
