from __future__ import annotations

import re
from collections.abc import Iterable

from pypinyin import lazy_pinyin

from .ir import Clause, Frame, Token, TranslationResult
from .lexicon import Lexicon, Phrase, Phrasebook
from .parser import parse_clause, split_clauses

INITIALS = (
    "zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l",
    "g", "k", "h", "j", "q", "x", "r", "z", "c", "s", "y", "w",
)
INITIAL_MAP = {
    "b": "p", "p": "p", "m": "m", "f": "p",
    "d": "k", "t": "k", "n": "n", "l": "n",
    "g": "k", "k": "k", "h": "k",
    "j": "k", "q": "k", "x": "k",
    "zh": "k", "ch": "k", "sh": "k", "r": "w",
    "z": "k", "c": "k", "s": "k",
    "y": "w", "w": "w",
}


class UnknownWordError(ValueError):
    pass


def _map_final(final: str) -> tuple[str, str]:
    final = final.replace("ü", "u").replace("v", "u")
    final = re.sub(r"\d", "", final)
    if final.startswith("er"):
        return "e", ""
    vowel = "a"
    for candidate in "aeiou":
        if candidate in final:
            vowel = candidate
            break
    coda = "n" if final.endswith(("n", "ng")) else ""
    return vowel, coda


def loanwordize(text: str) -> str:
    """把中文借词转写成合法鸭语音节，并用 kwaʔ 标记。"""
    syllables: list[str] = []
    for pinyin in lazy_pinyin(text):
        pinyin = re.sub(r"[^a-zü]", "", pinyin.lower())
        if not pinyin:
            continue
        initial = ""
        rest = pinyin
        for candidate in INITIALS:
            if pinyin.startswith(candidate):
                initial = candidate
                rest = pinyin[len(candidate):]
                break
        onset = INITIAL_MAP.get(initial, "k") if initial else ""
        vowel, coda = _map_final(rest)
        syllables.append(f"{onset}{vowel}{coda}")
    if not syllables:
        return "kwaʔ"
    return "kwaʔ-" + "-".join(syllables)


def _duck_of(zh: str | None, lexicon: Lexicon) -> str | None:
    if not zh:
        return None
    word = lexicon.lookup_base(zh)
    return word.duck if word else None


def _add(
    tokens: list[Token],
    zh: str | None,
    lexicon: Lexicon,
    warnings: list[str],
    strict: bool,
    *,
    kind: str = "word",
    gloss: str | None = None,
    emphasis: int = 0,
) -> None:
    if not zh:
        return
    if zh.isdigit():
        number = int(zh)
        duck = "ʔok" if number == 1 else "ʔok-ʔok" if number == 2 else "ʔok-ʔok-ʔok" if number == 3 else "kakaka"
        tokens.append(Token(duck, zh, kind, emphasis))
        return
    word = lexicon.lookup_base(zh)
    if word is None:
        if strict:
            raise UnknownWordError(f"未收录的词：{zh}")
        duck = loanwordize(zh)
        warnings.append(f"未收录：{zh} -> {duck}")
        tokens.append(Token(duck, f"[借]{zh}", "loan", emphasis))
        return

    text = word.duck
    if zh.endswith("们") and word.duck not in {"mama", "nana", "tata"}:
        text = f"{word.duck} {word.duck}"
    tokens.append(Token(text, gloss or zh, kind, emphasis))


def _particle(tokens: list[Token], duck: str, gloss: str) -> None:
    tokens.append(Token(duck, gloss, "particle"))


def _place_needs_ki(place: str | None, lexicon: Lexicon) -> bool:
    return _duck_of(place, lexicon) not in {"ʔa-ki", "ʔa-ʔo"}


def realize(
    frame: Frame,
    lexicon: Lexicon,
    strict: bool = False,
) -> tuple[list[Token], list[str]]:
    tokens: list[Token] = []
    warnings: list[str] = []

    def add(zh: str | None, *, kind: str = "word", gloss: str | None = None, emphasis: int = 0):
        _add(tokens, zh, lexicon, warnings, strict, kind=kind, gloss=gloss, emphasis=emphasis)

    def part(duck: str, gloss: str):
        _particle(tokens, duck, gloss)

    kind = frame.kind
    if kind == "stative":
        add(frame.subject)
        if frame.negation:
            part("ʔu", "不")
        add(frame.adjective, emphasis=frame.intensity)
        if frame.question:
            part("ha", "吗")
    elif kind == "equative":
        if frame.subject_parts:
            for part_zh in frame.subject_parts:
                add(part_zh)
        else:
            add(frame.subject)
        if frame.negation:
            part("ʔu", "不")
        add(frame.object)
        if frame.question:
            part("ha", "吗")
    elif kind == "possessive":
        add(frame.subject)
        add(frame.object)
    elif kind == "possess":
        add(frame.subject)
        add(frame.quantity)
        add(frame.object)
        if frame.negation:
            part("ʔu", "不")
        else:
            part("ki", "在")
        if frame.question:
            part("ha", "吗")
    elif kind == "exist_place":
        add(frame.place)
        if frame.place and _duck_of(frame.place, lexicon) not in {"ti", "ta", "ʔa-ki", "ʔa-ʔo"}:
            part("ki", "在")
        add(frame.quantity)
        add(frame.object)
        if frame.negation:
            part("ʔu", "不")
        if frame.question:
            part("ha", "吗")
    elif kind == "locative":
        add(frame.subject)
        add(frame.place)
        if frame.place and _place_needs_ki(frame.place, lexicon):
            part("ki", "在")
        if frame.negation:
            part("ʔu", "不")
        if frame.question:
            part("ha", "吗")
    elif kind in {"transitive", "intransitive"}:
        add(frame.subject)
        add(frame.quantity)
        if frame.adjective and frame.object:
            add(frame.adjective, emphasis=frame.intensity)
        add(frame.object)
        if frame.place:
            add(frame.place)
            if _place_needs_ki(frame.place, lexicon):
                part("ki", "在")
        add(frame.modifier)
        add(frame.manner)
        if frame.negation:
            part("ʔu", "不")
        add(frame.complement_verb)
        add(frame.verb)
        add(frame.modal)
        if frame.aspect == "perf":
            part("ko", "已")
        elif frame.aspect == "fut" and _duck_of(frame.verb, lexicon) != "ba":
            part("ba", "将")
        if frame.question:
            part("ha", "吗")
    elif kind == "noun_phrase":
        add(frame.quantity)
        add(frame.modifier)
        add(frame.object)
    elif kind == "fragment":
        add(frame.quantity)
        add(frame.modifier)
        for raw in frame.raw:
            add(raw)
        if frame.question:
            part("ha", "吗")
    elif kind == "wh_fragment":
        for raw in frame.raw:
            add(raw)
        part("ha", "吗")
    elif kind == "unknown_fragment":
        for raw in frame.raw:
            add(raw)
        if frame.question:
            part("ha", "吗")

    return tokens, warnings


def _phrase_clause(source: str, phrase: Phrase, punctuation: str | None = None) -> Clause:
    duck = phrase.duck.strip()
    phrase_punct = ""
    if duck and duck[-1] in "?!.。！？":
        phrase_punct = duck[-1]
        duck = duck[:-1].strip()

    parts = [part for part in duck.split() if part]
    glosses = list(phrase.gloss)
    tokens = [
        Token(part, glosses[index] if index < len(glosses) else "?", "word")
        for index, part in enumerate(parts)
    ]

    punct = phrase_punct or punctuation or "。"
    if punctuation and punctuation in "?？!":
        punct = punctuation

    emotion = phrase.emotion
    if punctuation == "!":
        emotion = "alarm" if any(w in source for w in ("危险", "救命", "小心")) else "excited"
    elif punctuation and punctuation in "?？":
        emotion = "question"
    return Clause(source, tokens, punct, emotion)


def _finalize_punctuation(frame: Frame) -> str:
    punct = frame.punctuation or "。"
    if frame.question:
        return "?"
    if frame.emotion in {"alarm", "excited"}:
        return "!"
    return punct


def translate(
    text: str,
    *,
    strict: bool = False,
    lexicon: Lexicon | None = None,
    phrasebook: Phrasebook | None = None,
) -> TranslationResult:
    text = text.strip()
    if not text:
        raise ValueError("请输入要翻译的中文。")

    lexicon = lexicon or Lexicon.load()
    phrasebook = phrasebook or Phrasebook.load()

    phrase = phrasebook.lookup(text)
    if phrase is not None:
        clause = _phrase_clause(text, phrase)
        return TranslationResult(text, [clause], [])

    clauses: list[Clause] = []
    warnings: list[str] = []
    for clause_text, punctuation in split_clauses(text):
        phrase = phrasebook.lookup(clause_text)
        if phrase is not None:
            clauses.append(_phrase_clause(clause_text, phrase, punctuation))
            continue

        frame = parse_clause(clause_text, punctuation, lexicon, strict=strict)
        if frame.kind == "empty":
            continue
        tokens, clause_warnings = realize(frame, lexicon, strict=strict)
        warnings.extend(clause_warnings)
        if not tokens:
            continue
        clauses.append(
            Clause(
                source=clause_text,
                tokens=tokens,
                punctuation=_finalize_punctuation(frame),
                emotion=frame.emotion,
            )
        )

    if not clauses:
        raise ValueError("没有可翻译的内容。")
    return TranslationResult(text, clauses, warnings)


def translate_many(texts: Iterable[str]) -> list[TranslationResult]:
    lexicon = Lexicon.load()
    phrasebook = Phrasebook.load()
    return [translate(text, lexicon=lexicon, phrasebook=phrasebook) for text in texts]
