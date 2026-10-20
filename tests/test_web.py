from fastapi.testclient import TestClient

from ducklang.web import app


def test_index_and_voices(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKLANG_WEB_AUDIO_DIR", str(tmp_path))
    with TestClient(app) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert "嘎语" in index.text

        voices = client.get("/api/voices")
        assert voices.status_code == 200
        payload = voices.json()
        assert {item["id"] for item in payload["voices"]} >= {"duckling", "adult"}
        assert "question" in {item["id"] for item in payload["emotions"]}


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
            json={"text": "你好吗？", "voice": "duckling", "emotion": None},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["duck"] == "na wi ha?"
        assert payload["gloss"] == "你 好 吗"
        assert payload["duration"] > 0.5
        assert payload["audio_url"].startswith("/api/audio/")

        audio = client.get(payload["audio_url"])
        assert audio.status_code == 200
        assert audio.headers["content-type"].startswith("audio/wav")
        assert len(audio.content) > 1000


def test_unknown_word_warning_and_strict_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKLANG_WEB_AUDIO_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/translate", json={"text": "我喝咖啡"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["warnings"]
        assert "kwaʔ" in payload["duck"]

        strict = client.post("/api/translate", json={"text": "我喝咖啡", "strict": True})
        assert strict.status_code == 400
        assert "未收录" in strict.json()["detail"]


def test_invalid_options_and_empty_text(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKLANG_WEB_AUDIO_DIR", str(tmp_path))
    with TestClient(app) as client:
        assert client.post("/api/translate", json={"text": "你好", "voice": "robot"}).status_code == 400
        assert (
            client.post("/api/translate", json={"text": "你好", "emotion": "angry"}).status_code
            == 400
        )
        assert client.post("/api/translate", json={"text": ""}).status_code == 422
        assert client.get("/api/audio/not-a-file.wav").status_code == 404
