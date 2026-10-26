"""鸭语 -> 中文。输出"鸭式中文"：意思对就行，不追求润色。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .lexicon import Lexicon, Phrasebook, Word
from .phonology import is_valid_word

_CLAUSE_RE = re.compile(r"([,.!?;，。！？；]+)")
GO_VERBS = {"wiiko", "wiki"}
MODIFIER_ZH = {"多": "很多"}


@dataclass
class ReverseClause:
    duck: str
    zh: str
    gloss: str


@dataclass
class ReverseResult:
    source: str
    clauses: list[ReverseClause]
    warnings: list[str] = field(default_factory=list)

    @property
    def zh(self) -> str:
        return "".join(clause.zh for clause in self.clauses)

    @property
    def gloss(self) -> str:
        return " / ".join(clause.gloss for clause in self.clauses)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "zh": self.zh,
            "gloss": self.gloss,
            "warnings": self.warnings,
            "clauses": [vars(clause) for clause in self.clauses],
        }


@dataclass
class _NP:
    head: Word
    modifiers: list[Word] = field(default_factory=list)

    @property
    def zh(self) -> str:
        mods = "".join(MODIFIER_ZH.get(m.zh, m.zh) for m in self.modifiers)
        return f"{mods}{self.head.zh}"

    @property
    def place_zh(self) -> str:
        mods = "".join(MODIFIER_ZH.get(m.zh, m.zh) for m in self.modifiers)
        return f"{mods}{self.head.place or self.head.zh}"


def _split_clauses(text: str) -> list[tuple[str, str]]:
    parts = _CLAUSE_RE.split(text.strip())
    clauses: list[tuple[str, str]] = []
    for i in range(0, len(parts), 2):
        body = parts[i].strip()
        punct = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            clauses.append((body, punct[:1]))
    return clauses


def _lex_words(words: list[str], lexicon: Lexicon, warnings: list[str]) -> list[Word | None]:
    """贪心匹配多词短语（如 wakaa kii = 饿）。后面还有动词时，kii 是助动词"要"，不并成短语。"""
    out: list[Word | None] = []
    i = 0
    while i < len(words):
        matched = None
        for size in range(min(lexicon.max_phrase_len, len(words) - i), 1, -1):
            candidate = lexicon.lookup_duck(" ".join(words[i:i + size]))
            if candidate is None:
                continue
            rest = [lexicon.lookup_duck(w) for w in words[i + size:]]
            if candidate.pos == "stative" and any(w is not None and w.pos == "v" for w in rest):
                continue
            matched, i = candidate, i + size
            break
        if matched is None:
            word = lexicon.lookup_duck(words[i])
            if word is None:
                reason = "未知鸭语词" if is_valid_word(words[i]) else "非法鸭语词"
                warnings.append(f"{reason}：{words[i]}")
            matched, i = word, i + 1
        out.append(matched)
    return out


def _reverse_clause(body: str, punct: str, lexicon: Lexicon, warnings: list[str]) -> ReverseClause:
    raw_words = body.split()
    items = _lex_words(raw_words, lexicon, warnings)
    words = [w for w in items if w is not None]
    gloss = " ".join(w.zh if w else "?" for w in items)

    question = punct in {"?", "？"}
    if words and words[-1].pos == "particle":
        question = True
        words = words[:-1]
    perf = any(w.pos == "aspect" for w in words)
    fut = any(w.pos == "fut" for w in words)
    words = [w for w in words if w.pos not in {"aspect", "fut", "particle"}]

    time = None
    if words and words[0].pos == "time":
        time, words = words[0], words[1:]

    has_verb = any(w.pos == "v" for w in words)
    nps: list[_NP] = []
    place: _NP | None = None
    partner: _NP | None = None
    verbs: list[Word] = []
    manner: Word | None = None
    predicate: Word | None = None
    negation = False
    wh = False

    for idx, word in enumerate(words):
        prev = words[idx - 1] if idx else None
        nxt = words[idx + 1] if idx + 1 < len(words) else None
        if word.pos in {"pron", "n", "q"}:
            wh = wh or word.pos == "q"
            nps.append(_NP(word))
        elif word.pos == "postp" and nps:
            place = nps.pop()
        elif word.pos == "conj" and nps:
            partner = nps.pop()
        elif word.pos == "neg":
            negation = True
        elif word.pos == "v":
            verbs.append(word)
        elif word.pos == "stative":
            after_noun = prev is not None and prev.pos in {"pron", "n"} and nps
            is_first_np = len(nps) == 1 and not verbs
            if after_noun and (word.zh == "多" or (has_verb and not (is_first_np and nxt
                                                                      and nxt.pos == "v"))):
                nps[-1].modifiers.append(word)
            elif has_verb and nxt is not None and nxt.pos == "v":
                manner = word
            elif predicate is None:
                predicate = word
            elif nps:
                nps[-1].modifiers.append(word)

    subject: _NP | None = None
    objects: list[_NP] = []
    if verbs:
        if len(nps) >= 2:
            subject, objects = nps[0], nps[1:]
        elif len(nps) == 1:
            np = nps[0]
            if np.head.pos == "pron" or np.head.animate:
                subject = np
            else:
                objects = [np]
    else:
        subject, objects = (nps[0], nps[1:]) if nps else (None, [])

    zh = ""
    if time:
        zh += time.zh
    if subject:
        zh += subject.zh
    if partner:
        zh += f"和{partner.zh}"

    when = next((o for o in objects if o.head.duck == "kikoo"), None)
    if when is not None:
        objects = [o for o in objects if o is not when]

    if verbs:
        if when is not None:
            zh += when.zh
        if negation:
            zh += "没" if perf or verbs[0].duck == "kawa" else "不"
        if fut:
            zh += "会"
        if manner:
            zh += manner.zh
        first = verbs[0]
        if place and first.duck not in GO_VERBS:
            zh += f"在{place.place_zh}"
        for i, verb in enumerate(verbs):
            zh += verb.zh
            if place and verb.duck in GO_VERBS and i == 0:
                zh += place.place_zh
        if verbs[-1].duck == "wika" and len(objects) >= 2:
            zh += objects[0].zh + "".join(o.zh for o in objects[1:])
        else:
            zh += "".join(o.zh for o in objects)
        if perf and not negation:
            zh += "了"
    elif predicate:
        zh += "".join(o.zh for o in objects)
        if negation:
            zh += "不"
        if fut:
            zh += "会"
        zh += predicate.zh
        if perf:
            zh += "了"
    elif place:
        zh += ("不" if negation else "") + f"在{place.place_zh}"
    else:
        rest = objects
        if subject is None and not rest and negation:
            zh += "不"
        if subject is not None and subject.head.pred and not objects:
            zh = zh[: -len(subject.zh)] + ("会" if fut else "") + subject.head.pred
        else:
            zh += "".join(o.zh for o in rest)
            if fut:
                zh += "会"
        if perf:
            zh += "了"

    if question:
        zh += "？" if wh else "吗？"
    elif punct in {"!", "！"}:
        zh += "！"
    elif punct in {",", "，"}:
        zh += "，"
    else:
        zh += "。"
    return ReverseClause(body, zh, gloss)


def reverse(
    text: str,
    *,
    lexicon: Lexicon | None = None,
    phrasebook: Phrasebook | None = None,
) -> ReverseResult:
    text = text.strip()
    if not text:
        raise ValueError("请输入要翻译的鸭语。")
    lexicon = lexicon or Lexicon.load()
    phrasebook = phrasebook or Phrasebook.load()

    clauses: list[ReverseClause] = []
    warnings: list[str] = []
    for body, punct in _split_clauses(text.lower()):
        phrase = phrasebook.lookup_duck(body)
        if phrase is not None:
            zh = phrase.zh[0]
            asks = any(q in zh for q in ("吗", "呢", "什么", "谁", "哪", "几"))
            if asks and (phrase.duck.endswith("?") or punct in {"?", "？"}):
                end = "？"
            elif punct in {"!", "！"} or phrase.duck.endswith("!"):
                end = "！"
            elif punct in {",", "，"}:
                end = "，"
            else:
                end = "。"
            gloss = " ".join(
                (lexicon.lookup_duck(w).zh if lexicon.lookup_duck(w) else "?") for w in body.split()
            )
            clauses.append(ReverseClause(body, zh + end, gloss))
            continue
        clauses.append(_reverse_clause(body, punct, lexicon, warnings))
    if not clauses:
        raise ValueError("没有可翻译的鸭语。")
    return ReverseResult(text, clauses, warnings)
