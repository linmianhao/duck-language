# 录音来源与授权

`data/voice_bank.npz` 中的频谱包络和起音瞬态由下列录音派生（`tools/build_bank.py`）。
原始录音放在 `samples/raw/`，不提交到仓库。

| 文件 | 作者 | 来源 | 授权 |
| --- | --- | --- | --- |
| Anas platyrhynchos - Mallard XC62258 | Jonathon Jongsma | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Anas_platyrhynchos_-_Mallard_XC62258.mp3)（原始出处 xeno-canto XC62258） | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |

由于原始录音采用 CC BY-SA，公开发布 `voice_bank.npz` 时需要保留以上署名，并以相同协议共享该文件。
换成自录音频后重新运行 `build_bank.py`，即可去掉这一约束。
