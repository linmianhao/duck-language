from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml


def data_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = (
        here.parent / "data",
        here.parents[2] / "data",
        Path.cwd() / "data",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("找不到 data 目录（lexicon.yaml / phrasebook.yaml）")


@dataclass(frozen=True)
class Word:
    duck: str
    glosses: tuple[str, ...]
    pos: str = "n"
    frame: tuple[str, ...] = ()


@dataclass(frozen=True)
class Phrase:
    zh: tuple[str, ...]
    duck: str
    gloss: tuple[str, ...]
    emotion: str = "neutral"


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\s\.,!?;:，。！？；：、'\"“”‘’~～]+", "", text)
    return text.strip()


class Lexicon:
    def __init__(self, words: Iterable[Word]):
        self.words = list(words)
        self.by_zh: dict[str, Word] = {}
        self.by_duck: dict[str, Word] = {}
        for word in self.words:
            self.by_duck.setdefault(word.duck, word)
            for gloss in word.glosses:
                self.by_zh.setdefault(gloss, word)

    def lookup(self, zh: str) -> Word | None:
        return self.by_zh.get(zh)

    def lookup_base(self, zh: str) -> Word | None:
        word = self.lookup(zh)
        if word is not None:
            return word
        if zh.endswith("们") and len(zh) > 1:
            return self.lookup(zh[:-1])
        return None

    @property
    def zh_words(self) -> list[str]:
        return list(self.by_zh)

    @classmethod
    def load(cls, path: Path | None = None) -> Lexicon:
        path = path or (data_dir() / "lexicon.yaml")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        words: list[Word] = []
        for item in raw:
            glosses = item.get("gloss") or []
            if isinstance(glosses, str):
                glosses = [glosses]
            words.append(
                Word(
                    duck=str(item["duck"]),
                    glosses=tuple(str(g) for g in glosses),
                    pos=str(item.get("pos", "n")),
                    frame=tuple(item.get("frame") or ()),
                )
            )
        return cls(words)


class Phrasebook:
    def __init__(self, phrases: Iterable[Phrase]):
        self.phrases = list(phrases)
        self.by_zh: dict[str, Phrase] = {}
        for phrase in self.phrases:
            for zh in phrase.zh:
                self.by_zh.setdefault(normalize_key(zh), phrase)

    def lookup(self, text: str) -> Phrase | None:
        return self.by_zh.get(normalize_key(text))

    @classmethod
    def load(cls, path: Path | None = None) -> Phrasebook:
        path = path or (data_dir() / "phrasebook.yaml")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        phrases: list[Phrase] = []
        for item in raw:
            zh = item["zh"]
            if isinstance(zh, str):
                zh = [zh]
            gloss = item.get("gloss") or []
            if isinstance(gloss, str):
                gloss = gloss.split()
            phrases.append(
                Phrase(
                    zh=tuple(str(z) for z in zh),
                    duck=str(item["duck"]),
                    gloss=tuple(str(g) for g in gloss),
                    emotion=str(item.get("emotion", "neutral")),
                )
            )
        return cls(phrases)


def load_all() -> tuple[Lexicon, Phrasebook]:
    return Lexicon.load(), Phrasebook.load()
