# ducklang

中文 -> 嘎语翻译器，并用程序化方式合成真正的鸭子叫声。

## 安装

```bash
cd D:\duck-lang
uv sync
```

## 使用

```bash
uv run duck "你好吗？"
uv run duck "我饿了"
uv run duck "明天要下雨"
uv run duck --voice duckling "我喜欢你"
uv run duck --no-play --save out\demo.wav "危险！"
uv run duck --json "你吃了吗？"
uv run duck
```

省略文本会进入 REPL：

```text
中文> 我饿了
中文：我饿了
鸭语：ma mam ʔi
直译：我 食物 要
音频：D:\duck-lang\out\duck-20261020-153000-123.wav（已播放）
```

## Web 界面

```bash
uv run duck-web
```

浏览器打开 `http://127.0.0.1:8000`。页面里可以输入中文、选择音色和情绪，点击“翻译并嘎一声”后会显示鸭语、直译、警告，并直接播放合成出来的鸭叫。API 文档在 `http://127.0.0.1:8000/docs`，默认只监听本机。

```bash
uv run duck-web --host 0.0.0.0 --port 8080
uv run duck-web --reload
```

Web API：

- `POST /api/translate`：`{"text": "你好吗？", "voice": "duckling", "emotion": null}`
- `GET /api/audio/{filename}`：返回生成的 WAV
- `GET /api/voices`：音色与情绪列表
- `GET /api/health`：健康检查

## Python API

```python
from ducklang import speak, translate

result = translate("我饿了")
print(result.duck)   # ma mam ʔi
print(result.gloss)  # 我 食物 要

speech = speak("你好吗？", voice="duckling")
print(speech.path, speech.played)
```

## 音色

```bash
uv run duck --voices
```

- `duckling`：幼鸭，高、快
- `adult`：成鸭，默认
- `angry`：愤怒，粗糙、更响
- `soft`：温柔，低、慢

## 翻译规则

- 中文 SVO -> 鸭语 SOV
- `不/没/别` -> `ʔu`
- `了` -> `ko`
- `要/将/明天` -> `ba`
- `吗` -> 句末 `ha`
- 处所用后置词 `ki`
- 数量 1-3 用 `ʔok` 重叠，超过三用 `kakaka`
- 未收录词用拼音转写成合法鸭语音节，并加 `kwaʔ` 借词标记

词典在 `data/lexicon.yaml`，高频整句在 `data/phrasebook.yaml`。

## 发声

`src/ducklang/synth.py` 用 numpy 做源-滤波器合成：脉冲声源、按元音设置的共振峰、爆破音/鼻音/喉塞音，以及情绪相关的音高和时长。输出 44.1kHz / 16-bit 单声道 WAV，Windows 下用 `winsound` 播放。

## 测试

```bash
uv run pytest
uv run ruff check .
```
