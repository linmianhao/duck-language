# 嘎语翻译器使用指南

本文覆盖 CLI、REPL、Web 页面、Python API、翻译规则、词典扩展和测试。想先看效果和产品介绍，请回到 [README](README.md)。

## 安装

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
cd D:\duck-lang
uv sync
```

## 命令行

### 基本用法

```bash
uv run duck "你好吗？"
uv run duck "我饿了"
uv run duck "明天要下雨"
uv run duck --voice duckling "我喜欢你"
uv run duck --no-play --save out\demo.wav "危险！"
uv run duck --json "你吃了吗？"
```

输出示例：

```text
中文：我饿了
鸭语：ma mam ʔi。
直译：我 食物 要
音频：D:\duck-lang\out\duck-20261020-153000-123.wav（已播放）
```

如果当前环境没有可用音频设备，WAV 仍会保存，终端会提示文件路径。

### 选项

| 选项 | 说明 |
| --- | --- |
| `text` | 要翻译的中文；省略时进入 REPL |
| `--save`, `-s` | 指定 WAV 保存路径 |
| `--no-play` | 只生成 WAV，不播放 |
| `--gloss/--no-gloss` | 显示或隐藏逐词直译，默认显示 |
| `--voice`, `-v` | 音色：`duckling`、`adult`、`angry`、`soft` |
| `--emotion`, `-e` | 覆盖情绪：`neutral`、`question`、`excited`、`alarm`、`soft` |
| `--strict` | 遇到未收录词直接报错，不自动借词化 |
| `--json` | 输出 JSON，便于脚本调用 |
| `--voices` | 列出音色参数 |
| `--help` | 查看帮助 |

### REPL

```bash
uv run duck
```

```text
中文> 我饿了
中文：我饿了
鸭语：ma mam ʔi。
直译：我 食物 要
音频：D:\duck-lang\out\duck-20261020-153000-123.wav（已播放）
中文> q
```

输入 `q`、`quit` 或 `exit` 退出。通过管道传入多行文本时，每一行会作为一个短句处理。

### JSON 输出

```bash
uv run duck --json "你吃了吗？"
```

```json
{
  "source": "你吃了吗？",
  "duck": "na num ko ha?",
  "gloss": "你 吃 了 吗",
  "warnings": [],
  "clauses": [
    {
      "source": "你吃了吗？",
      "duck": "na num ko ha?",
      "gloss": "你 吃 了 吗",
      "emotion": "question"
    }
  ],
  "audio": "D:\\duck-lang\\out\\duck-20261020-153000-123.wav",
  "played": true
}
```

## Web 界面

### 启动

```bash
uv run duck-web
```

浏览器打开 `http://127.0.0.1:8000`。默认只监听本机。

```bash
uv run duck-web --host 0.0.0.0 --port 8080
uv run duck-web --reload
```

API 文档在 `http://127.0.0.1:8000/docs`。

### 页面功能

- 输入中文，或点击示例句直接翻译
- 选择音色和情绪
- 自动播放合成出来的鸭叫
- 查看鸭语、逐词直译和借词警告
- 复制鸭语、下载 WAV
- 最近 5 条记录，点击可重播

### Web API

翻译：

```http
POST /api/translate
Content-Type: application/json

{
  "text": "你好吗？",
  "voice": "duckling",
  "emotion": null,
  "strict": false
}
```

响应：

```json
{
  "source": "你好吗？",
  "duck": "na wi ha?",
  "gloss": "你 好 吗",
  "warnings": [],
  "audio_url": "/api/audio/duck-web-0123456789ab.wav",
  "voice": "duckling",
  "emotion": null,
  "duration": 0.861
}
```

其他接口：

- `GET /api/audio/{filename}`：播放或下载生成的 WAV
- `GET /api/voices`：音色、情绪列表和参数
- `GET /api/health`：健康检查

Web 生成的音频默认写入 `out/`。可以通过环境变量指定目录：

```powershell
$env:DUCKLANG_WEB_AUDIO_DIR = "D:\duck-lang\out\web"
uv run duck-web
```

## Python API

```python
from ducklang import speak, translate

result = translate("我饿了")
print(result.duck)    # ma mam ʔi。
print(result.gloss)   # 我 食物 要
print(result.warnings)

speech = speak("你好吗？", voice="duckling", play=False)
print(speech.result.duck)
print(speech.path)
print(speech.played)
```

`translate(text, strict=False)` 返回 `TranslationResult`；`speak(...)` 会翻译、合成并可选播放，返回 `Speech` 对象。

## 音色与情绪

### 音色

| 名称 | 特点 |
| --- | --- |
| `duckling` | 幼鸭，音高更高、语速更快 |
| `adult` | 成鸭，默认音色 |
| `angry` | 愤怒鸭，更粗糙、更响 |
| `soft` | 温柔鸭，更低、更慢 |

### 情绪

| 名称 | 效果 |
| --- | --- |
| `neutral` | 平静 |
| `question` | 疑问，句尾上扬 |
| `excited` | 兴奋，音高和音量提高 |
| `alarm` | 警报，更快更响 |
| `soft` | 温柔，更低更慢 |

不指定情绪时，会根据标点和句子内容自动判断。

## 翻译规则

- 中文 SVO 转鸭语 SOV
- `不/没/别` 用 `ʔu`，放在动词前
- `了` 用 `ko`
- `要/将/明天` 用 `ba`
- `吗` 用句末 `ha`
- 处所用后置词 `ki`
- 数量 1–3 用 `ʔok` 重叠，超过三用 `kakaka`
- 复数用重叠
- 未收录词用拼音转写成合法鸭语音节，并加 `kwaʔ` 借词标记
- 长句按标点和连词拆成多个短句

几个例子：

| 中文 | 嘎语 | 直译 |
| --- | --- | --- |
| 你好吗？ | `na wi ha?` | 你 好 吗 |
| 你吃了吗？ | `na num ko ha?` | 你 吃 了 吗 |
| 我不冷 | `ma ʔu pim` | 我 不 冷 |
| 我们没有食物 | `mama mam ʔu` | 我们 食物 不 |
| 我喜欢吃鱼 | `ma nam num wi` | 我 鱼 吃 喜欢 |
| 明天要下雨 | `ʔo-wa ba` | 下雨 将 |
| 我们去水边吧 | `mama wa ki ba` | 我们 水边 在 去 |

## 词典与短语库

### 词典

`data/lexicon.yaml` 存放词根。每条包含鸭语写法、中文释义、词性和可选语义角色：

```yaml
- duck: num
  gloss: [吃, 喝]
  pos: v
  frame: [agent, patient]

- duck: wa
  gloss: [水, 河, 湖]
  pos: n
```

常见词性：`pron`、`n`、`v`、`stative`、`q`、`num`、`quant`、`neg`、`particle`、`aspect`、`postp`、`interj`。

### 短语库

`data/phrasebook.yaml` 存放高频整句。匹配时会忽略标点和空格：

```yaml
- zh: [你好, 您好, 嗨]
  duck: na wi ha?
  gloss: [你, 好, 吗]
  emotion: question
```

新增词条后不需要改代码，重新运行即可。`gloss` 列表与 `duck` 的空格分词按顺序对应。

## 发声实现

`src/ducklang/synth.py` 用 numpy 做程序化源-滤波器合成：

- 脉冲声源，带音高轮廓和轻微抖动
- 按元音 `a/e/i/o/u` 设置共振峰
- `k/p/t` 爆破音、`m/n` 鼻音、`ʔ` 喉塞、`h` 气息、`w` 滑音
- 情绪控制音高、时长和音量
- 输出 44.1kHz / 16-bit 单声道 WAV

Windows 下用内置 `winsound` 播放；其他平台会尝试 `sounddevice`，没有音频设备时保留 WAV。

## 测试与检查

```bash
uv run pytest
uv run ruff check .
```

## 项目结构

```text
D:\duck-lang
├─ src/ducklang/
│  ├─ cli.py            # 命令行与 REPL
│  ├─ web.py            # FastAPI Web 服务
│  ├─ static/           # 前端页面
│  ├─ translator.py     # 中文 -> 鸭语
│  ├─ parser.py         # 分句、分词、槽位
│  ├─ lexicon.py        # 词典加载
│  ├─ phonology.py      # 音节合法性
│  ├─ prosody.py        # 情绪与韵律
│  ├─ synth.py          # 鸭叫合成
│  └─ player.py         # WAV 播放
├─ data/
│  ├─ lexicon.yaml
│  └─ phrasebook.yaml
├─ docs/
│  └─ screenshot.png
├─ tests/
├─ out/
├─ README.md
├─ USAGE.md
├─ 方案设计.md
└─ pyproject.toml
```

## 常见问题

### 没有声音

先确认 `out/` 下有新生成的 WAV。Windows 下播放依赖 `winsound`；远程桌面、无音频设备或权限受限时可能无法播放，但 WAV 仍会保存。

### 端口被占用

换一个端口：

```bash
uv run duck-web --port 8080
```

### 浏览器没有自动播放

浏览器可能拦截自动播放。点击页面里的播放器即可，或保持页面上的“生成后自动播放”勾选并在点击按钮后等待结果。

### 未收录词

默认会借词化并在结果里显示警告。需要严格模式时：

```bash
uv run duck --strict "我喝咖啡"
```

### 翻译不准确

当前是规则翻译，优先覆盖日常表达。复杂书面语可能拆分得不完美；可以先把句子改短，或在 `data/lexicon.yaml` / `data/phrasebook.yaml` 中补充词条。
