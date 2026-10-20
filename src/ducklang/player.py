from __future__ import annotations

import sys
from pathlib import Path


def play_wav(path: Path) -> bool:
    """播放 WAV。成功返回 True；没有可用音频设备时返回 False。"""
    path = Path(path)
    if not path.exists():
        return False

    if sys.platform == "win32":
        try:
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return True
        except (OSError, RuntimeError):
            return False

    try:
        import sounddevice as sd
        import soundfile as sf

        data, samplerate = sf.read(str(path), dtype="float32")
        sd.play(data, samplerate)
        sd.wait()
        return True
    except (ImportError, OSError, RuntimeError):
        return False
