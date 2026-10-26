from __future__ import annotations

import itertools
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .phonology import feature_distance, parse_word, split_words


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
    animate: bool = False
    pred: str | None = None
    place: str | None = None
    placeholder: bool = False

    @property
    def zh(self) -> str:
        """反向翻译时的标准中文。"""
        return self.glosses[0]

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.duck.split())


@dataclass(frozen=True)
class Phrase:
    zh: tuple[str, ...]
    duck: str
    emotion: str = "neutral"

    @property
    def duck_key(self) -> str:
        return normalize_duck(self.duck)


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\s\.,!?;:，。！？；：、'\"“”‘’~～]+", "", text)
    return text.strip()


def normalize_duck(text: str) -> str:
    return " ".join(split_words(text.lower()))


# 关键词：与同一语法位置的其他词至少相差 2 个声学特征
CRITICAL = ("危险", "不", "吗", "要", "了")
# 同一语法位置的词性分组（不同位置的词靠语法区分，允许只差 1 个特征）
SLOT_GROUPS = {
    "pron": "nominal", "n": "nominal", "q": "nominal",
    "v": "verb", "stative": "predicate",
    "neg": "pre_verb", "fut": "post_verb", "aspect": "post_verb",
    "particle": "final", "postp": "postp", "conj": "postp", "time": "time",
}


class Lexicon:
    def __init__(self, words: Iterable[Word]):
        self.words = list(words)
        self.by_zh: dict[str, Word] = {}
        self.by_duck: dict[str, Word] = {}
        for word in self.words:
            self.by_duck.setdefault(word.duck, word)
            for gloss in word.glosses:
                self.by_zh.setdefault(gloss, word)
        self.max_phrase_len = max((len(w.parts) for w in self.words), default=1)
        self.placeholder_noun = next(
            (w for w in self.words if w.placeholder and w.pos == "n"), None
        )
        self.placeholder_verb = next(
            (w for w in self.words if w.placeholder and w.pos == "v"), None
        )

    def lookup(self, zh: str) -> Word | None:
        return self.by_zh.get(zh)

    def lookup_base(self, zh: str) -> Word | None:
        word = self.lookup(zh)
        if word is not None:
            return word
        if zh.endswith("们") and len(zh) > 1:
            return self.lookup(zh[:-1])
        return None

    def lookup_duck(self, duck: str) -> Word | None:
        return self.by_duck.get(duck)

    def single_words(self) -> list[Word]:
        return [w for w in self.words if len(w.parts) == 1]

    def nearest(self, duck: str, max_distance: int = 1) -> Word | None:
        """按声学特征找最近的单词条，用于解码纠错；有并列时返回 None。"""
        best: list[tuple[int, Word]] = []
        for word in self.single_words():
            try:
                distance = feature_distance(duck, word.duck)
            except ValueError:
                continue
            if distance <= max_distance:
                best.append((distance, word))
        if not best:
            return None
        best.sort(key=lambda item: item[0])
        if len(best) > 1 and best[0][0] == best[1][0]:
            return None
        return best[0][1]

    @property
    def zh_words(self) -> list[str]:
        return list(self.by_zh)

    def validate(self) -> list[str]:
        """返回词典问题列表；空列表表示通过。"""
        problems: list[str] = []
        seen_duck: dict[str, Word] = {}
        seen_zh: dict[str, Word] = {}
        for word in self.words:
            if word.duck in seen_duck:
                problems.append(f"鸭语重复：{word.duck}")
            seen_duck[word.duck] = word
            for gloss in word.glosses:
                if gloss in seen_zh:
                    problems.append(f"中文重复：{gloss}（{seen_zh[gloss].duck} / {word.duck}）")
                seen_zh[gloss] = word
            for part in word.parts:
                try:
                    syllables = parse_word(part)
                except ValueError as exc:
                    problems.append(str(exc))
                    continue
                reduplicated = len(syllables) == 2 and syllables[0] == syllables[1]
                if reduplicated and word.pos != "pron" and word.zh != "危险":
                    problems.append(f"非复数代词或警报却是重叠形式：{part}")
            if len(word.parts) > 1 and not all(self.lookup_duck(p) for p in word.parts):
                problems.append(f"短语里有未定义的词：{word.duck}")

        singles = self.single_words()
        for a, b in itertools.combinations(singles, 2):
            if SLOT_GROUPS.get(a.pos) != SLOT_GROUPS.get(b.pos):
                continue
            if a.zh not in CRITICAL and b.zh not in CRITICAL:
                continue
            if feature_distance(a.duck, b.duck) < 2:
                problems.append(f"关键词距离不足：{a.duck}({a.zh}) / {b.duck}({b.zh})")
        return problems

    @classmethod
    def load(cls, path: Path | None = None) -> Lexicon:
        path = path or (data_dir() / "lexicon.yaml")
        return _load_lexicon(str(path))


@lru_cache(maxsize=4)
def _load_lexicon(path: str) -> Lexicon:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    words: list[Word] = []
    for item in raw:
        glosses = item.get("gloss") or []
        if isinstance(glosses, str):
            glosses = [glosses]
        words.append(
            Word(
                duck=normalize_duck(str(item["duck"])),
                glosses=tuple(str(g) for g in glosses),
                pos=str(item.get("pos", "n")),
                animate=bool(item.get("animate", False)),
                pred=item.get("pred"),
                place=item.get("place"),
                placeholder=bool(item.get("placeholder", False)),
            )
        )
    return Lexicon(words)


class Phrasebook:
    def __init__(self, phrases: Iterable[Phrase]):
        self.phrases = list(phrases)
        self.by_zh: dict[str, Phrase] = {}
        self.by_duck: dict[str, Phrase] = {}
        for phrase in self.phrases:
            self.by_duck.setdefault(phrase.duck_key, phrase)
            for zh in phrase.zh:
                self.by_zh.setdefault(normalize_key(zh), phrase)

    def lookup(self, text: str) -> Phrase | None:
        return self.by_zh.get(normalize_key(text))

    def lookup_duck(self, duck: str) -> Phrase | None:
        return self.by_duck.get(normalize_duck(duck))

    def validate(self, lexicon: Lexicon) -> list[str]:
        problems: list[str] = []
        seen: set[str] = set()
        for phrase in self.phrases:
            if phrase.duck_key in seen:
                problems.append(f"短语库鸭语重复：{phrase.duck}")
            seen.add(phrase.duck_key)
            for part in phrase.duck_key.split():
                if lexicon.lookup_duck(part) is None:
                    problems.append(f"短语库用了词典外的词：{part}（{phrase.zh[0]}）")
        return problems

    @classmethod
    def load(cls, path: Path | None = None) -> Phrasebook:
        path = path or (data_dir() / "phrasebook.yaml")
        return _load_phrasebook(str(path))


@lru_cache(maxsize=4)
def _load_phrasebook(path: str) -> Phrasebook:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    phrases: list[Phrase] = []
    for item in raw:
        zh = item["zh"]
        if isinstance(zh, str):
            zh = [zh]
        phrases.append(
            Phrase(
                zh=tuple(str(z) for z in zh),
                duck=str(item["duck"]).strip(),
                emotion=str(item.get("emotion", "neutral")),
            )
        )
    return Phrasebook(phrases)


def load_all() -> tuple[Lexicon, Phrasebook]:
    return Lexicon.load(), Phrasebook.load()
