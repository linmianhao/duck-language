from __future__ import annotations

import argparse
import os
import re
import uuid
import wave
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .prosody import EMOTIONS, VOICES
from .synth import render_result
from .translator import UnknownWordError, translate

STATIC_DIR = Path(__file__).resolve().parent / "static"
AUDIO_RE = re.compile(r"^duck-web-[0-9a-f]{12}\.wav$")

VOICE_LABELS = {
    "duckling": "幼鸭",
    "adult": "成鸭",
    "angry": "愤怒鸭",
    "soft": "温柔鸭",
}
EMOTION_LABELS = {
    "neutral": "平静",
    "question": "疑问",
    "excited": "兴奋",
    "alarm": "警报",
    "soft": "温柔",
}

app = FastAPI(title="嘎语翻译器", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    voice: str = "adult"
    emotion: str | None = None
    strict: bool = False


class TranslateResponse(BaseModel):
    source: str
    duck: str
    gloss: str
    warnings: list[str]
    audio_url: str
    voice: str
    emotion: str | None = None
    duration: float


def _audio_dir() -> Path:
    override = os.environ.get("DUCKLANG_WEB_AUDIO_DIR")
    if override:
        directory = Path(override)
    else:
        root = Path(__file__).resolve().parents[2]
        directory = root / "out" if (root / "pyproject.toml").exists() else Path.cwd() / "out"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


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
            {
                "id": name,
                "label": VOICE_LABELS.get(name, name),
                "f0": preset.f0,
                "speed": preset.speed,
                "rough": preset.rough,
            }
            for name, preset in VOICES.items()
        ],
        "emotions": [
            {"id": name, "label": EMOTION_LABELS.get(name, name)}
            for name in EMOTIONS
        ],
    }


@app.post("/api/translate", response_model=TranslateResponse)
def api_translate(request: TranslateRequest) -> TranslateResponse:
    if request.voice not in VOICES:
        raise HTTPException(status_code=400, detail=f"未知音色：{request.voice}")
    if request.emotion is not None and request.emotion not in EMOTIONS:
        raise HTTPException(status_code=400, detail=f"未知情绪：{request.emotion}")

    try:
        result = translate(request.text, strict=request.strict)
    except UnknownWordError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = f"duck-web-{uuid.uuid4().hex[:12]}.wav"
    path = _audio_dir() / filename
    render_result(result, voice=request.voice, emotion=request.emotion, out_path=path)

    return TranslateResponse(
        source=result.source,
        duck=result.duck,
        gloss=result.gloss,
        warnings=result.warnings,
        audio_url=f"/api/audio/{filename}",
        voice=request.voice,
        emotion=request.emotion,
        duration=round(_duration(path), 3),
    )


@app.get("/api/audio/{filename}")
def audio(filename: str) -> FileResponse:
    if not AUDIO_RE.fullmatch(filename):
        raise HTTPException(status_code=404, detail="音频不存在")
    path = _audio_dir() / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="音频不存在")
    return FileResponse(
        path,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
