from __future__ import annotations

import logging
import re

import jieba

from .ir import Frame
from .lexicon import Lexicon

_jieba_ready = False

PRONOUNS = {
    "我", "我们", "咱们", "你", "您", "你们", "他", "她", "它",
    "他们", "她们", "它们", "大家", "自己",
}
NEGATIONS = {"不", "没", "没有", "别", "不要", "不能", "不会", "未", "无"}
NEG_HAVE = {"没有"}
NEG_MODAL = {"不能", "不会"}
PERF = {"了", "过", "已经", "曾经"}
FUT_TIME = {"明天", "以后", "下次", "将来", "待会", "马上", "将要"}
WANT_OR_FUT = {"要", "想", "想要"}
MODAL_OR_FUT = {"会"}
MODALS = {"能", "可以"}
COPULA = {"是"}
HAVE = {"有"}
PREPS = {"在", "到", "往", "向", "从"}
INTENS = {"很", "太", "非常", "特别", "真的", "真", "十分"}
QUESTION_PARTICLES = {"吗", "呢", "么"}
MEASURE = {"个", "只", "条", "杯", "碗", "点", "些", "位", "名", "张", "件", "颗", "朵", "群"}
STOP = {
    "的", "地", "得", "和", "跟", "与", "把", "被", "给", "让", "着",
    "啊", "呀", "哦", "啦", "嘛", "吧", "边", "里", "中", "外", "上",
    "下", "前", "后", "面", "旁", "就", "也", "都", "还", "又", "再",
}
CONJUNCTIONS = {"因为", "所以", "但是", "可是", "不过", "然后", "而且", "如果", "那么"}
PLACE_WORDS = {
    "水", "河", "湖", "池塘", "水塘", "家", "窝", "巢", "房子", "这里",
    "这儿", "那里", "那", "这", "外面", "里面", "河边", "水边",
}
SPLIT_RE = re.compile(
    r"([。！？!?；;，,.\n、]|因为|所以|但是|可是|不过|然后|而且|如果)"
)


def _ensure_jieba(lexicon: Lexicon) -> None:
    global _jieba_ready
    if _jieba_ready:
        return
    jieba.setLogLevel(logging.ERROR)
    for word in lexicon.zh_words:
        if len(word) > 1:
            jieba.add_word(word, freq=100_000)
    _jieba_ready = True


def normalize_text(text: str) -> str:
    table = str.maketrans({
        "，": ",", "。": ".", "！": "!", "？": "?", "；": ";", "：": ":",
        "、": ",", "“": '"', "”": '"', "‘": "'", "’": "'",
    })
    return text.translate(table).strip()


def split_clauses(text: str) -> list[tuple[str, str]]:
    """按标点和常见连词分句，返回 (子句, 标点)。"""
    parts = SPLIT_RE.split(normalize_text(text))
    clauses: list[tuple[str, str]] = []
    buffer = ""

    for part in parts:
        if not part:
            continue
        if SPLIT_RE.fullmatch(part):
            clause = _strip_leading_conjunctions(buffer)
            if clause:
                clauses.append((clause, _normalize_punct(part)))
            buffer = ""
        else:
            buffer += part

    clause = _strip_leading_conjunctions(buffer)
    if clause:
        clauses.append((clause, "。"))
    return clauses


def _normalize_punct(punct: str) -> str:
    if punct in CONJUNCTIONS:
        return ","
    if punct in ".。":
        return "。"
    return punct


def _strip_leading_conjunctions(text: str) -> str:
    text = text.strip()
    changed = True
    while changed:
        changed = False
        for word in CONJUNCTIONS | {"就", "那", "还有"}:
            if text.startswith(word):
                text = text[len(word):].strip()
                changed = True
    return text


def _known_vocabulary(lexicon: Lexicon) -> set[str]:
    known = set(lexicon.zh_words)
    known |= PRONOUNS | NEGATIONS | PERF | FUT_TIME | WANT_OR_FUT | MODAL_OR_FUT
    known |= MODALS | COPULA | HAVE | PREPS | INTENS | QUESTION_PARTICLES
    known |= MEASURE | STOP | CONJUNCTIONS | PLACE_WORDS
    known |= {"一", "二", "两", "三", "四", "五", "六", "七", "八", "九", "十"}
    return known


def _split_token(token: str, known: set[str]) -> list[str]:
    if token in known:
        return [token]

    parts: list[str] = []
    index = 0
    while index < len(token):
        match = None
        for end in range(len(token), index, -1):
            candidate = token[index:end]
            if candidate in known:
                match = candidate
                break
        if match is not None:
            parts.append(match)
            index += len(match)
            continue

        start = index
        index += 1
        while index < len(token):
            if any(token[index:end] in known for end in range(len(token), index, -1)):
                break
            index += 1
        parts.append(token[start:index])
    return parts


def tokenize(text: str, lexicon: Lexicon) -> list[str]:
    _ensure_jieba(lexicon)
    raw = jieba.lcut(text.strip())
    known = _known_vocabulary(lexicon)
    tokens: list[str] = []
    for token in raw:
        token = token.strip()
        if not token:
            continue
        if re.fullmatch(r"[\W_]+", token, flags=re.UNICODE):
            continue
        if token in {"，", "。", "！", "？", "；", "：", "、", ",", ".", "!", "?", ";", ":"}:
            continue
        tokens.extend(_split_token(token, known))
    return tokens


def classify(token: str, lexicon: Lexicon) -> str:
    if token.isdigit():
        return "num"
    if token in PRONOUNS:
        return "pron"
    if token in NEG_HAVE:
        return "neg_have"
    if token in NEG_MODAL:
        return "neg_modal"
    if token in NEGATIONS:
        return "neg"
    if token in QUESTION_PARTICLES:
        return "particle"
    if token in MEASURE:
        return "measure"
    if token in PERF:
        return "perf"
    if token in FUT_TIME:
        return "fut"
    if token in WANT_OR_FUT:
        return "want_or_fut"
    if token in MODAL_OR_FUT:
        return "modal_or_fut"
    if token in MODALS:
        return "modal"
    if token in COPULA:
        return "copula"
    if token in HAVE:
        return "have"
    if token in PREPS:
        return "prep"
    if token in INTENS:
        return "intensity"
    if token in STOP:
        return "stop"

    word = lexicon.lookup_base(token)
    if word is None:
        return "unknown"
    return {
        "pron": "pron",
        "n": "noun",
        "v": "verb",
        "stative": "stative",
        "q": "q",
        "num": "num",
        "quant": "quant",
        "neg": "neg",
        "particle": "particle",
        "aspect": "perf",
        "postp": "prep",
        "interj": "interj",
    }.get(word.pos, "unknown")


def detect_emotion(text: str, punct: str, is_question: bool = False) -> str:
    if any(word in text for word in ("危险", "救命", "小心", "快跑", "别", "不要")):
        return "alarm"
    if punct == "!" or "！" in punct:
        return "excited"
    if is_question or punct in "?？":
        return "question"
    if any(word in text for word in ("喜欢", "爱", "谢谢", "抱", "亲", "贴", "乖", "晚安")):
        return "soft"
    return "neutral"


def _duck_of(zh: str, lexicon: Lexicon) -> str | None:
    word = lexicon.lookup_base(zh)
    return word.duck if word else None


def is_place(zh: str | None, lexicon: Lexicon) -> bool:
    if not zh:
        return False
    if zh in PLACE_WORDS:
        return True
    duck = _duck_of(zh, lexicon)
    return duck in {"wa", "nu", "wa-nu", "ti", "ta"}


def is_go(zh: str | None, lexicon: Lexicon) -> bool:
    return _duck_of(zh or "", lexicon) == "ba"


def parse_clause(
    text: str,
    punctuation: str,
    lexicon: Lexicon,
    strict: bool = False,
) -> Frame:
    tokens = tokenize(text, lexicon)
    frame = Frame(source=text, punctuation=punctuation or "。")
    if not tokens:
        frame.kind = "empty"
        return frame

    tagged = [(token, classify(token, lexicon)) for token in tokens]
    frame.raw = list(tokens)

    subject: str | None = None
    obj: str | None = None
    place: str | None = None
    verb: str | None = None
    complement_verb: str | None = None
    adjective: str | None = None
    modifier: str | None = None
    manner: str | None = None
    quantity: str | None = None
    qword: str | None = None
    negation = False
    aspect: str | None = None
    modal: str | None = None
    question: str | None = (
        "yesno" if (punctuation and punctuation in "?？") or text.endswith(("吗", "呢")) else None
    )
    intensity = 0
    copula = False
    have = False
    prep: str | None = None
    has_de = "的" in tokens
    subject_index: int | None = None
    adj_index: int | None = None
    unknown: list[str] = []

    def set_subject(token: str, index: int) -> None:
        nonlocal subject, subject_index
        subject = token
        subject_index = index

    def set_object(token: str) -> None:
        nonlocal obj, place
        if prep is not None and place is None:
            place = token
        elif obj is None:
            obj = token
        elif place is None:
            place = token
        else:
            unknown.append(token)

    i = 0
    while i < len(tagged):
        token, role = tagged[i]
        nxt = tagged[i + 1] if i + 1 < len(tagged) else None

        if token == "好" and nxt and nxt[1] == "stative":
            intensity = max(intensity, 1)
            i += 1
            continue

        if role in {"pron", "noun"}:
            if subject is None and verb is None and not copula and not have:
                set_subject(token, i)
            else:
                set_object(token)
        elif role in {"num", "quant"}:
            quantity = token
        elif role == "measure":
            pass
        elif role == "neg":
            negation = True
            if token == "没" and nxt and nxt[1] in {"verb", "modal"}:
                aspect = "perf"
        elif role == "neg_have":
            negation = True
            if nxt and nxt[1] in {"verb", "modal", "modal_or_fut"}:
                aspect = "perf"
            else:
                have = True
        elif role == "neg_modal":
            negation = True
            modal = "能"
        elif role == "perf":
            aspect = "perf"
        elif role == "fut":
            aspect = "fut"
        elif role == "want_or_fut":
            if nxt and nxt[1] in {"verb", "modal", "modal_or_fut"}:
                aspect = "fut"
            elif nxt and nxt[1] in {"noun", "pron", "q", "unknown"}:
                verb = token
            else:
                verb = token
        elif role == "modal_or_fut":
            if any(r == "fut" for _, r in tagged):
                aspect = "fut"
            else:
                modal = token
        elif role == "modal":
            modal = token
        elif role == "verb":
            if verb is None:
                verb = token
            elif complement_verb is None:
                complement_verb = token
            else:
                unknown.append(token)
        elif role == "stative":
            if adjective is None:
                adjective = token
                adj_index = i
            elif modifier is None and obj is None:
                modifier = token
            else:
                unknown.append(token)
        elif role == "q":
            qword = token
            question = "wh"
            duck = _duck_of(token, lexicon)
            if duck in {"ʔa-ki", "ʔa-ʔo"}:
                if place is None:
                    place = token
            elif duck == "ʔa-ba":
                manner = token
            elif duck == "ʔa-ʔok":
                quantity = token
            else:
                if obj is None:
                    obj = token
        elif role == "particle":
            if token in QUESTION_PARTICLES:
                question = question or "yesno"
        elif role == "copula":
            copula = True
        elif role == "have":
            have = True
        elif role == "prep":
            prep = token
        elif role == "intensity":
            intensity = max(intensity, 2 if token in {"太", "非常", "特别", "十分"} else 1)
        elif role in {"interj", "stop"}:
            pass
        elif role == "unknown":
            unknown.append(token)
            if verb is not None and obj is None:
                obj = token
            elif subject is None and not copula and not have:
                set_subject(token, i)
            elif obj is None:
                obj = token
        i += 1

    if have and adjective is not None and obj is None:
        obj = adjective
        adjective = None

    if is_go(verb, lexicon) and obj is not None and is_place(obj, lexicon):
        place = obj
        obj = None
    if is_go(complement_verb, lexicon) and obj is not None and is_place(obj, lexicon):
        place = obj
        obj = None

    frame.subject = subject
    frame.object = obj
    frame.place = place
    frame.verb = verb
    frame.complement_verb = complement_verb
    frame.adjective = adjective
    frame.modifier = modifier
    frame.manner = manner
    frame.quantity = quantity
    frame.negation = negation
    frame.aspect = aspect
    frame.modal = modal
    frame.question = question
    frame.intensity = intensity
    frame.copula = copula
    frame.have = have
    frame.unknown = unknown

    if copula and has_de and subject is not None and obj is not None and place is not None:
        frame.kind = "equative"
        frame.subject_parts = [subject, obj]
        frame.subject = None
        frame.object = place
        frame.place = None
    elif have:
        if is_place(subject, lexicon):
            frame.kind = "exist_place"
            frame.place = subject
            frame.subject = None
        else:
            frame.kind = "possess"
    elif copula:
        frame.kind = "stative" if adjective is not None and obj is None else "equative"
    elif adjective is not None and verb is None:
        if (
            subject is not None
            and adj_index is not None
            and subject_index is not None
            and adj_index < subject_index
            and not negation
            and aspect is None
        ):
            frame.kind = "noun_phrase"
            frame.modifier = adjective
            frame.object = subject
            frame.subject = None
            frame.adjective = None
        else:
            frame.kind = "stative"
    elif verb is not None:
        frame.kind = "transitive" if obj is not None else "intransitive"
    elif subject is not None and place is not None and adjective is None:
        frame.kind = "locative"
    elif subject is not None and obj is not None:
        frame.kind = "possessive" if has_de else "equative"
    elif subject is not None:
        frame.kind = "fragment"
        frame.raw = [subject]
    elif adjective is not None:
        frame.kind = "stative"
    elif qword is not None:
        frame.kind = "wh_fragment"
        frame.raw = [qword]
    elif quantity is not None:
        frame.kind = "fragment"
    elif unknown:
        frame.kind = "unknown_fragment"
        frame.raw = unknown
    else:
        frame.kind = "fragment"

    frame.emotion = detect_emotion(text, punctuation, question is not None)
    return frame
