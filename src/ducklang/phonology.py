from __future__ import annotations

import re
from dataclasses import dataclass

ONSETS = ("p", "b", "m", "t", "k", "g", "h", "w", "ʔ", "n")
VOWELS = ("a", "e", "i", "o", "u")
CODAS = ("k", "m", "n", "ʔ")
ONSET_CHARS = set(ONSETS)
VOWEL_CHARS = set(VOWELS)
CODA_CHARS = set(CODAS)

@dataclass(frozen=True)
class Syllable:
    onset: str
    vowel: str
    coda: str
    length: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    emphasis: int = 0

    @property
    def text(self) -> str:
        return f"{self.onset}{self.vowel}{self.coda}"


def _syllabify_part(part: str) -> list[Syllable]:
    syllables: list[Syllable] = []
    index = 0
    while index < len(part):
        onset = ""
        if part[index] in ONSET_CHARS:
            onset = part[index]
            index += 1
            if index < len(part) and part[index] == "w" and onset != "w":
                onset += "w"
                index += 1

        if index >= len(part) or part[index] not in VOWEL_CHARS:
            raise ValueError(f"非法鸭语音节：{part!r}")
        vowel = part[index]
        index += 1

        coda = ""
        if index < len(part) and part[index] in CODA_CHARS:
            next_is_vowel = index + 1 < len(part) and part[index + 1] in VOWEL_CHARS
            next_is_glide = (
                index + 2 < len(part)
                and part[index + 1] == "w"
                and part[index + 2] in VOWEL_CHARS
            )
            if not next_is_vowel and not next_is_glide:
                coda = part[index]
                index += 1

        syllables.append(Syllable(onset=onset, vowel=vowel, coda=coda))
    return syllables


def parse_word(word: str) -> list[Syllable]:
    """把一个鸭语词拆成音节。支持用 - 连接的复合词和连续音节。"""
    cleaned = word.strip(" \t\r\n.,!?;:。！？；：、")
    if not cleaned:
        return []

    syllables: list[Syllable] = []
    for part in cleaned.split("-"):
        if part:
            syllables.extend(_syllabify_part(part))
    return syllables


def parse_text(text: str) -> list[Syllable]:
    """拆解整句鸭语，忽略标点和空白。"""
    syllables: list[Syllable] = []
    for token in re.split(r"[\s,.;:!?。！？；：、]+", text):
        if token:
            syllables.extend(parse_word(token))
    return syllables


def is_valid_word(word: str) -> bool:
    try:
        return bool(parse_word(word))
    except ValueError:
        return False


def validate_text(text: str) -> None:
    for token in re.split(r"[\s,.;:!?。！？；：、]+", text):
        if token:
            parse_word(token)
