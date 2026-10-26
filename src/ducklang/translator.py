from __future__ import annotations

from collections.abc import Iterable

from .ir import Clause, Frame, NounPhrase, Token, TranslationResult
from .lexicon import Lexicon, Phrase, Phrasebook
from .parser import parse_clause, split_clauses


class UnknownWordError(ValueError):
    pass


class _Builder:
    def __init__(self, lexicon: Lexicon, strict: bool):
        self.lexicon = lexicon
        self.strict = strict
        self.tokens: list[Token] = []
        self.warnings: list[str] = []

    def word(
        self, zh: str | None, *, emphasis: int = 0, as_verb: bool = False, agent: bool = False
    ) -> str | None:
        if not zh:
            return None
        word = self.lexicon.lookup_base(zh)
        if word is None:
            if self.strict:
                raise UnknownWordError(f"未收录的词：{zh}")
            if as_verb:
                word = self.lexicon.placeholder_verb
            elif agent:
                word = self.lexicon.lookup("人") or self.lexicon.placeholder_noun
            else:
                word = self.lexicon.placeholder_noun
            if word is None:
                raise UnknownWordError(f"未收录的词：{zh}（词典缺少占位词）")
            self.warnings.append(f"未收录：{zh} -> {word.duck}（{word.zh}）")
            self.tokens.append(Token(word.duck, f"[{word.zh}]{zh}", "placeholder", emphasis))
            return word.duck
        text = word.duck
        if zh.endswith("们") and word.pos != "pron" and len(zh) > 1:
            self.tokens.append(Token(text, zh[:-1], "word", emphasis))
            self.tokens.append(Token(self.lexicon.lookup("多").duck, "们", "word"))
            return text
        self.tokens.append(Token(text, zh, "word", emphasis))
        return text

    def particle(self, zh: str) -> None:
        word = self.lexicon.lookup(zh)
        assert word is not None, zh
        self.tokens.append(Token(word.duck, zh, "particle"))

    def noun_phrase(self, np: NounPhrase | None, *, agent: bool = False) -> str | None:
        if np is None:
            return None
        duck = self.word(np.head, agent=agent)
        for modifier in np.modifiers:
            self.word(modifier)
        return duck


def realize(frame: Frame, lexicon: Lexicon, strict: bool = False) -> tuple[list[Token], list[str]]:
    b = _Builder(lexicon, strict)
    unknown = set(frame.unknown)

    # 子句里没有动词和谓语时，主语后面的未知词当作动作（"我 ??" -> 我 做）
    verbs = list(frame.verbs)
    objects = list(frame.objects)
    if not verbs and frame.predicate is None and frame.subject is not None:
        for np in list(objects):
            if np.head in unknown:
                objects.remove(np)
                verbs.append(np.head)
                break

    b.word(frame.time)
    b.noun_phrase(frame.subject, agent=True)
    if frame.partner is not None:
        b.noun_phrase(frame.partner)
        b.particle("和")

    if frame.kind == "locative":
        if frame.negation:
            b.particle("不")
        b.noun_phrase(frame.place)
        b.particle("在")
    else:
        for np in objects:
            b.noun_phrase(np)
        if frame.place is not None:
            b.noun_phrase(frame.place)
            place_word = lexicon.lookup_base(frame.place.head)
            if place_word is None or place_word.pos != "q":
                b.particle("在")
        if frame.negation:
            b.particle("不")
        if frame.kind == "stative":
            b.word(frame.predicate, emphasis=frame.intensity)
        if frame.manner:
            b.word(frame.manner)
        for verb in verbs:
            b.word(verb, as_verb=True)

    if frame.aspect == "perf":
        b.particle("了")
    elif frame.aspect == "fut":
        b.particle("会")
    if frame.question:
        b.particle("吗")

    for zh in frame.dropped:
        b.warnings.append(f"未表达：{zh}")
    return b.tokens, b.warnings


def _phrase_clause(source: str, phrase: Phrase, lexicon: Lexicon, punctuation: str | None) -> Clause:
    duck = phrase.duck.strip()
    phrase_punct = ""
    if duck and duck[-1] in "?!.。！？":
        phrase_punct = duck[-1]
        duck = duck[:-1].strip()
    tokens = []
    for part in duck.split():
        word = lexicon.lookup_duck(part)
        tokens.append(Token(part, word.zh if word else "?", "word"))

    punct = phrase_punct or punctuation or "。"
    if punctuation in {"?", "？", "!"}:
        punct = punctuation
    emotion = phrase.emotion
    if punctuation == "!" and emotion not in {"alarm"}:
        emotion = "excited"
    elif punctuation in {"?", "？"}:
        emotion = "question"
    return Clause(source, tokens, punct, emotion)


def _finalize_punctuation(frame: Frame) -> str:
    if frame.question:
        return "?"
    if frame.emotion in {"alarm", "excited"}:
        return "!"
    return frame.punctuation or "。"


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
        return TranslationResult(text, [_phrase_clause(text, phrase, lexicon, None)], [])

    clauses: list[Clause] = []
    warnings: list[str] = []
    for clause_text, punctuation in split_clauses(text):
        phrase = phrasebook.lookup(clause_text)
        if phrase is not None:
            clauses.append(_phrase_clause(clause_text, phrase, lexicon, punctuation))
            continue
        frame = parse_clause(clause_text, punctuation, lexicon)
        if frame.kind == "empty":
            continue
        tokens, clause_warnings = realize(frame, lexicon, strict=strict)
        warnings.extend(clause_warnings)
        if tokens:
            clauses.append(
                Clause(clause_text, tokens, _finalize_punctuation(frame), frame.emotion)
            )

    if not clauses:
        raise ValueError("没有可翻译的内容。")
    return TranslationResult(text, clauses, warnings)


def translate_many(texts: Iterable[str]) -> list[TranslationResult]:
    lexicon = Lexicon.load()
    phrasebook = Phrasebook.load()
    return [translate(text, lexicon=lexicon, phrasebook=phrasebook) for text in texts]
