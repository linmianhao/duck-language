# 嘎语翻译器使用指南

本文覆盖 CLI、REPL、Web 页面、Python API、嘎语规则、词典扩展、音色库和测试。想先看效果和产品介绍，请回到 [README](README.md)；设计思路见 [方案设计](方案设计.md)。

## 安装

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
cd E:\xgo-duck\duck-language
uv sync
```

## 命令行

### 三个方向

```bash
uv run duck "你去哪里？"                   # 中文 -> 鸭语 + 鸭叫
uv run duck --reverse "wa kiwo wiiko ki?"  # 鸭语 -> 中文（同时合成鸭叫）
uv run duck --listen out\demo.wav          # 鸭叫录音 -> 鸭语 -> 中文
```

输出示例：

```text
中文：你去哪里？
鸭语：wa kiwo wiiko ki?
直译：你 哪里 去 吗
音频：out\duck-20261026-153000-123.wav（已播放）
```

```text
音频：out\demo.wav
鸭语：wa kiwo wiiko ki?
中文：你去哪里？
置信度：80%（6 个音节）
```

如果当前环境没有可用音频设备，WAV 仍会保存，终端会提示文件路径。

### 选项

| 选项 | 说明 |
| --- | --- |
| `text` | 要翻译的文本；省略时进入 REPL |
| `--reverse`, `-r` | 鸭语 -> 中文 |
| `--listen`, `-l` | 解码一个 WAV 文件 |
| `--save`, `-s` | 指定 WAV 保存路径 |
| `--no-play` | 只生成 WAV，不播放 |
| `--gloss/--no-gloss` | 显示或隐藏逐词直译，默认显示 |
| `--voice`, `-v` | 音色：`duckling`、`adult`、`angry`、`soft` |
| `--emotion`, `-e` | 覆盖情绪：`neutral`、`question`、`excited`、`alarm`、`soft` |
| `--target`, `-t` | 播放设备：`pc`（默认）或 `robot`（机器人小喇叭，去掉 300 Hz 以下） |
| `--strict` | 遇到未收录词直接报错，不用占位词 |
| `--json` | 输出 JSON，便于脚本调用 |
| `--voices` | 列出音色参数 |

### REPL

```bash
uv run duck              # 中文 REPL
uv run duck --reverse    # 鸭语 REPL
```

输入 `q`、`quit` 或 `exit` 退出。通过管道传入多行文本时，每一行会作为一个短句处理。

## Web 界面

```bash
uv run duck-web
```

浏览器打开 `http://127.0.0.1:8000`。默认只监听本机；API 文档在 `/docs`。

页面顶部切换三个方向：

- **中 → 鸭**：输入中文，生成鸭语和鸭叫；可选音色、情绪、播放设备
- **鸭 → 中**：输入鸭语，翻成中文并合成对应鸭叫
- **听 → 中**：上传 WAV 或直接用麦克风录音，解码成鸭语和中文，显示置信度

### Web API

| 接口 | 说明 |
| --- | --- |
| `POST /api/translate` | `{"text", "voice", "emotion", "strict", "target"}` -> 鸭语、直译、音频地址 |
| `POST /api/reverse` | `{"text", "voice", "emotion", "target"}` -> 中文、直译、音频地址 |
| `POST /api/decode` | 请求体为 WAV 原始字节（`Content-Type: audio/wav`，≤ 10 MB）-> 鸭语、中文、置信度、逐音节测量值 |
| `GET /api/audio/{filename}` | 播放或下载生成的 WAV |
| `GET /api/voices` | 音色、情绪、播放设备列表 |
| `GET /api/health` | 健康检查 |

Web 生成的音频写入 `out/`，只保留最近 200 个。可以用环境变量换目录：

```powershell
$env:DUCKLANG_WEB_AUDIO_DIR = "E:\xgo-duck\duck-language\out\web"
uv run duck-web
```

## Python API

```python
from ducklang import decode, render, reverse, speak, translate

r = translate("你饿吗？")
print(r.duck)            # wa wakaa kii ki?
print(r.gloss)           # 你 饿 吗
print(r.words)           # ['wa', 'wakaa', 'kii', 'ki']

print(reverse("ka waawi kii waka").zh)   # 我要吃鱼。

wav = render(r, voice="adult", target="robot")   # 也可以传鸭语字符串
d = decode(wav)
print(d.duck, d.zh, d.confidence)

speech = speak("危险！", voice="angry", play=False)
print(speech.path)
```

## 嘎语速查

### 音节

每个音节就是一声鸭叫，由三个特征组成：

| | 降 `a` | 升 `i` | 平 `o` |
|---|---|---|---|
| 亮·短 `k` | `ka` | `ki` | `ko` |
| 亮·长 | `kaa` | `kii` | `koo` |
| 暗·短 `w` | `wa` | `wi` | `wo` |
| 暗·长 | `waa` | `wii` | `woo` |

词由 1–2 个音节连写（如 `kiiwa` = 小鸭）。情绪只改变整体音高、音量、语速和沙哑程度，不改变这三个特征，所以任何情绪下都能解码。

### 语法

| 规则 | 示例 |
| --- | --- |
| 主语 宾语 动词（SOV） | 我吃鱼 -> `ka waawi waka` |
| 时间词放句首 | 明天我们去河边玩 -> `kiwoo kaka waa woko wiiko woka` |
| 修饰语在名词后 | 大鱼 -> `waawi koowa` |
| `ko` 不/没，放在动词或状态词前 | 我不冷 -> `ka ko kooki` |
| `koo` 了（完成）、`kiko` 会（将来），放在动词后 | 你吃了吗？ -> `wa waka koo ki?` |
| 处所 = 名词 + `woko`；伙伴 = 名词 + `kowo` | 我和你去玩 -> `ka wa kowo wiiko woka` |
| 问句句末加 `ki`；疑问词留在原位 | 你去哪里？ -> `wa kiwo wiiko ki?` |
| 复合需求用短语 | 饿 = `wakaa kii`（食物 要），渴 = `waa kii`，累 = `woo kii` |
| 代词复数用重叠 | 我们 = `kaka`，他们 = `kowa kowa` |

### 未收录词

嘎语只有约 60 个词，不做拼音借词（12 个音节表达不了中文读音，也翻不回来）。未收录的词按位置换成占位词并给出提示：

- 主语位置 -> `wowa`（人），例如"张三来了" -> `wowa wiki koo`
- 其他名词 -> `waawo`（东西），例如"我喝咖啡" -> `ka waawo waki`
- 没有其他动词时 -> `kiwaa`（做）

需要严格模式时用 `--strict`。

## 词典与短语库

### 词典 `data/lexicon.yaml`

```yaml
- duck: waka
  gloss: [吃, 啃]      # 第一个是反向翻译的标准译法
  pos: v
- duck: waa
  gloss: [水, 河, 湖, 水边]
  pos: n
  place: 水边          # 作处所时的中文
- duck: wakaa kii      # 多个词组成的短语
  gloss: [饿, 饥饿]
  pos: stative
```

规则（由 `tests/test_lexicon.py` 检查）：

1. 鸭语写法和中文释义都必须全局唯一（双向唯一，才能反向翻译）；
2. 每个词都能切分成合法音节；
3. 除代词复数和"危险"`kaakaa` 以外，不允许重叠形式；
4. 关键词（危险、不、吗、要、了）与同一语法位置的其他词至少相差 2 个声学特征。

### 短语库 `data/phrasebook.yaml`

```yaml
- zh: [你好, 您好, 你好吗]   # 第一个是反向翻译的标准译法
  duck: wa wi ki?
  emotion: question
```

同一句鸭语只能出现在一个条目里。新增词条不需要改代码。

## 发声与解码

### 合成（`synth.py`）

源 - 滤波混合合成，48 kHz / 16-bit 单声道：

- **声源（程序化）**：谐波丰富的脉冲序列，基频曲线按走势精确生成（降 / 升约 ±8 个半音）
- **粗糙度（程序化）**：25–42 Hz 深度调幅 + 抖动，做出"嘎"的沙哑感
- **声道滤波（真实录音）**：`data/voice_bank.npz` 里从真实绿头鸭录音提取的频谱包络（亮峰约 1.9 kHz，暗峰约 1.2 kHz）
- **起音（真实录音）**：真实鸭叫开头 15 ms 的瞬态

时长：短音 120 ms、长音 320 ms；静音：词内 60 ms、词间 200 ms、子句间 500 ms。

### 重建音色库

把录音放进 `samples/raw/`（不进 git），然后：

```bash
uv run --group tools python tools/build_bank.py samples/raw/*.mp3
```

没有 `voice_bank.npz` 时会退回内置的程序化包络，仍然可以工作。录音来源和授权见 [samples/ATTRIBUTION.md](samples/ATTRIBUTION.md)。

### 解码（`decoder.py`）

纯信号处理：带通 -> 能量检测（音色突变处再切开）-> 每个音节测时长、YIN 基频斜率（Theil-Sen）、频谱重心 -> 12 类音节 -> 按静音长度分词 -> 词典纠错（声学距离 1 且唯一）-> 反向翻译。

在模拟信道（`channel.py`：小喇叭频响 + 房间混响 + 噪声）下的实测：

| 信道 | 音节准确率 |
| --- | --- |
| 无损 | 100% |
| SNR 15 dB，RT60 0.2 s | 100% |
| SNR 10 dB，RT60 0.35 s | 100% |
| SNR 6 dB，RT60 0.5 s | 约 95% |

## 测试与检查

```bash
uv run pytest
uv run ruff check src tests tools
```

## 项目结构

```text
E:\xgo-duck\duck-language
├─ src/ducklang/
│  ├─ cli.py            # 命令行与 REPL
│  ├─ api.py            # Python API
│  ├─ web.py            # FastAPI Web 服务
│  ├─ static/           # 前端页面
│  ├─ phonology.py      # 12 音节、切分、声学距离
│  ├─ lexicon.py        # 双向词典、短语库、校验
│  ├─ parser.py         # 中文分句、分词、槽位
│  ├─ ir.py             # 语义框架
│  ├─ translator.py     # 中文 -> 鸭语
│  ├─ reverse.py        # 鸭语 -> 中文
│  ├─ prosody.py        # 音色与情绪（表情通道）
│  ├─ synth.py          # 混合鸭叫合成
│  ├─ decoder.py        # 声音 -> 鸭语
│  ├─ channel.py        # 喇叭/房间/噪声信道模拟
│  └─ player.py         # WAV 播放
├─ data/  lexicon.yaml · phrasebook.yaml · voice_bank.npz
├─ samples/  ATTRIBUTION.md · raw/（原始录音，不进 git）
├─ tools/  build_bank.py
├─ tests/
├─ README.md · USAGE.md · 方案设计.md
└─ pyproject.toml
```

## 常见问题

### 没有声音

先确认 `out/` 下有新生成的 WAV。Windows 下播放依赖 `winsound`；远程桌面、无音频设备或权限受限时可能无法播放，但 WAV 仍会保存。

### 解码结果不对

- 录音时关掉系统的降噪 / 回声消除 / 自动增益（网页录音已默认关闭）；
- 麦克风离喇叭近一点，环境安静一点；
- 用 `--json` 查看每个音节的时长、基频斜率和频谱重心，对照 `decoder.py` 顶部的阈值。

### 端口被占用

```bash
uv run duck-web --port 8080
```

### 浏览器没有自动播放

浏览器可能拦截自动播放，点击页面里的播放器即可。
