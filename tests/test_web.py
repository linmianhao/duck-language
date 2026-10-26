from fastapi.testclient import TestClient

from ducklang.synth import render_duck
from ducklang.web import app


def test_index_and_voices(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKLANG_WEB_AUDIO_DIR", str(tmp_path))
    with TestClient(app) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert "嘎语" in index.text
        assert "听 → 中" in index.text

        payload = client.get("/api/voices").json()
        assert {item["id"] for item in payload["voices"]} >= {"duckling", "adult"}
        assert "question" in {item["id"] for item in payload["emotions"]}
        assert {item["id"] for item in payload["targets"]} == {"pc", "robot"}


def test_static_assets_and_api_docs():
    with TestClient(app) as client:
        favicon = client.get("/static/favicon.svg")
        assert favicon.status_code == 200
        assert "svg" in favicon.headers["content-type"]
        assert client.get("/docs").status_code == 200


def test_translate_and_fetch_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKLANG_WEB_AUDIO_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/translate",
            json={"text": "你吃了吗？", "voice": "duckling", "emotion": None, "target": "robot"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["duck"] == "wa waka koo ki?"
        assert payload["gloss"] == "你 吃 了 吗"
        assert payload["duration"] > 0.5

        audio = client.get(payload["audio_url"])
        assert audio.status_code == 200
        assert audio.headers["content-type"].startswith("audio/wav")
        assert len(audio.content) > 1000


def test_reverse(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKLANG_WEB_AUDIO_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/reverse", json={"text": "wa kiwo wiiko ki?"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["zh"] == "你去哪里？"
        assert payload["audio_url"].startswith("/api/audio/")

        bad = client.post("/api/reverse", json={"text": "ma mam ʔi"}).json()
        assert bad["warnings"]
        assert bad["audio_url"] is None


def test_decode_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKLANG_WEB_AUDIO_DIR", str(tmp_path))
    wav = render_duck("ka wakaa kii", out_path=tmp_path / "in.wav").read_bytes()
    with TestClient(app) as client:
        response = client.post("/api/decode", content=wav,
                               headers={"Content-Type": "audio/wav"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["duck"] == "ka wakaa kii。"
        assert payload["zh"] == "我饿了。"
        assert len(payload["syllables"]) == 4

        assert client.post("/api/decode", content=b"not a wav").status_code == 400
        assert client.post("/api/decode", content=b"").status_code == 400


def test_unknown_word_warning_and_strict_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKLANG_WEB_AUDIO_DIR", str(tmp_path))
    with TestClient(app) as client:
        payload = client.post("/api/translate", json={"text": "我喝咖啡"}).json()
        assert payload["warnings"]
        assert payload["duck"] == "ka waawo waki。"

        strict = client.post("/api/translate", json={"text": "我喝咖啡", "strict": True})
        assert strict.status_code == 400
        assert "未收录" in strict.json()["detail"]


def test_invalid_options_and_empty_text(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKLANG_WEB_AUDIO_DIR", str(tmp_path))
    with TestClient(app) as client:
        assert client.post("/api/translate", json={"text": "你好", "voice": "robot"}).status_code == 400
        assert client.post("/api/translate", json={"text": "你好", "emotion": "angry"}).status_code == 400
        assert client.post("/api/translate", json={"text": "你好", "target": "tv"}).status_code == 400
        assert client.post("/api/translate", json={"text": ""}).status_code == 422
        assert client.get("/api/audio/not-a-file.wav").status_code == 404
