"""嘎语声学音系：12 个音节 = 音色(k 亮 / w 暗) × 走势(a 降 / i 升 / o 平) × 时长(短 / 长)。

每个音节就是一声鸭叫。音色、走势、时长是信息通道，任何情绪都不能改动它们；
整体音高、音量、语速、粗糙度属于表情通道，由 prosody 负责。
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

TIMBRES = ("k", "w")  # k = 亮"嘎"，w = 暗"呱"
CONTOURS = ("a", "i", "o")  # a = 降，i = 升，o = 平
TIMBRE_NAMES = {"k": "亮", "w": "暗"}
CONTOUR_NAMES = {"a": "降", "i": "升", "o": "平"}

_SYLLABLE_RE = re.compile(r"([kw])([aio])(\2?)")
_SPLIT_RE = re.compile(r"[\s,.;:!?。，！？；：、]+")


@dataclass(frozen=True)
class Syllable:
    timbre: str
    contour: str
    long: bool = False
    # 表情通道：不改变音节身份
    pitch: float = 1.0
    volume: float = 1.0
    tempo: float = 1.0
    rough: float = 1.0

    @property
    def text(self) -> str:
        return f"{self.timbre}{self.contour * (2 if self.long else 1)}"

    @property
    def features(self) -> tuple[str, str, bool]:
        return (self.timbre, self.contour, self.long)

    @property
    def description(self) -> str:
        return f"{TIMBRE_NAMES[self.timbre]}{CONTOUR_NAMES[self.contour]}{'长' if self.long else '短'}"


ALL_SYLLABLES: tuple[Syllable, ...] = tuple(
    Syllable(t, c, long) for t, long, c in itertools.product(TIMBRES, (False, True), CONTOURS)
)


def parse_word(word: str) -> list[Syllable]:
    """把一个鸭语词拆成音节；非法时抛出 ValueError。"""
    cleaned = word.strip(" \t\r\n.,!?;:。！？；：、")
    if not cleaned:
        return []
    syllables: list[Syllable] = []
    pos = 0
    for match in _SYLLABLE_RE.finditer(cleaned):
        if match.start() != pos:
            break
        syllables.append(Syllable(match.group(1), match.group(2), bool(match.group(3))))
        pos = match.end()
    if pos != len(cleaned):
        raise ValueError(f"非法鸭语词：{word!r}")
    return syllables


def split_words(text: str) -> list[str]:
    return [token for token in _SPLIT_RE.split(text) if token]


def parse_text(text: str) -> list[Syllable]:
    """拆解整句鸭语，忽略标点和空白。"""
    syllables: list[Syllable] = []
    for token in split_words(text):
        syllables.extend(parse_word(token))
    return syllables


def is_valid_word(word: str) -> bool:
    try:
        return bool(parse_word(word))
    except ValueError:
        return False


def validate_text(text: str) -> None:
    for token in split_words(text):
        parse_word(token)


def word_from_syllables(syllables: list[Syllable]) -> str:
    return "".join(s.text for s in syllables)


def feature_distance(a: str, b: str) -> int:
    """两个词之间不同的声学特征个数；音节数不同时视为无穷远。"""
    sa, sb = parse_word(a), parse_word(b)
    if len(sa) != len(sb):
        return 99
    return sum(
        (x.timbre != y.timbre) + (x.contour != y.contour) + (x.long != y.long)
        for x, y in zip(sa, sb, strict=True)
    )
