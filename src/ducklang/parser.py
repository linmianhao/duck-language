from __future__ import annotations

import logging
import re

import jieba

from .ir import Frame, NounPhrase
from .lexicon import Lexicon

_jieba_ready: set[int] = set()

NEGATIONS = {"不", "没", "没有", "别", "不要", "不能", "不会", "未", "无", "不用"}
PERF = {"了", "过", "已经", "曾经"}
FUT = {"会", "将", "将要", "快要"}
WANT = {"要", "想", "想要", "需要"}
COPULA = {"是"}
PREPS = {"在", "到", "往", "向"}
PARTNER = {"和", "跟", "与", "同"}
INTENS = {"很", "太", "非常", "特别", "真的", "真", "十分", "超", "好"}
STRONG_INTENS = {"太", "非常", "特别", "十分", "超"}
QUESTION_PARTICLES = {"吗", "呢", "么"}
NUM_ONE = {"一", "1"}
MEASURE = {"个", "只", "条", "杯", "碗", "点", "些", "位", "名", "张", "件", "颗", "朵", "群", "头"}
# 吞掉不报警的虚词
STOP = {
    "的", "地", "得", "着", "啊", "呀", "哦", "啦", "嘛", "吧", "哇", "呗",
    "边", "里", "中", "外", "上", "下", "前", "后", "面", "旁", "从",
    "就", "也", "都", "还", "又", "再", "把", "被", "让", "能", "可以", "请", "一起", "一下",
}
CONJUNCTIONS = {"因为", "所以", "但是", "可是", "不过", "然后", "而且", "如果", "那么"}
WEATHER = {"下雨", "雨"}
GO_VERBS = {"wiiko", "wiki"}
SPLIT_RE = re.compile(
    r"([。！？!?；;，,.\n、]|因为|所以|但是|可是|不过|然后|而且|如果)"
)
FUNCTION_WORDS = (
    NEGATIONS | PERF | FUT | WANT | COPULA | PREPS | PARTNER | INTENS
    | QUESTION_PARTICLES | MEASURE | STOP | CONJUNCTIONS
)


def _ensure_jieba(lexicon: Lexicon) -> None:
    if id(lexicon) in _jieba_ready:
        return
    jieba.setLogLevel(logging.ERROR)
    for word in list(lexicon.zh_words) + list(FUNCTION_WORDS):
        if len(word) > 1:
            jieba.add_word(word, freq=100_000)
    _jieba_ready.add(id(lexicon))


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
    if punct in CONJUNCTIONS or punct in ";；、":
        return ","
    if punct in ".。\n":
        return "。"
    return punct


def _strip_leading_conjunctions(text: str) -> str:
    text = text.strip()
    changed = True
    while changed:
        changed = False
        for word in CONJUNCTIONS | {"就", "那么", "还有"}:
            if text.startswith(word):
                text = text[len(word):].strip()
                changed = True
    return text


NUM_RE = re.compile(r"^([一二两三四五六七八九十几百千俩\d]+)(" + "|".join(MEASURE) + ")?$")


def _known_vocabulary(lexicon: Lexicon) -> set[str]:
    # 数字和量词不参与拆分未知词，避免"张三"被拆成"张 / 三"
    return set(lexicon.zh_words) | (FUNCTION_WORDS - MEASURE)


def _split_token(token: str, known: set[str]) -> list[str]:
    if token in known:
        return [token]
    parts: list[str] = []
    index = 0
    while index < len(token):
        match = None
        for end in range(len(token), index, -1):
            if token[index:end] in known:
                match = token[index:end]
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
    # 只由单字拆出来的"已知词"不可信（例如人名），整体当作未知词
    if len(token) > 1 and all(len(p) == 1 for p in parts) and any(p not in known for p in parts):
        return [token]
    return parts


def tokenize(text: str, lexicon: Lexicon) -> list[str]:
    _ensure_jieba(lexicon)
    known = _known_vocabulary(lexicon)
    tokens: list[str] = []
    for token in jieba.lcut(text.strip()):
        token = token.strip()
        if not token or re.fullmatch(r"[\W_]+", token, flags=re.UNICODE):
            continue
        number = NUM_RE.match(token)
        if number:
            tokens.extend(part for part in number.groups() if part)
            continue
        tokens.extend(_split_token(token, known))
    return tokens


def classify(token: str, lexicon: Lexicon) -> str:
    if token in NUM_ONE:
        return "one"
    if NUM_RE.match(token) and not NUM_RE.match(token).group(2):
        return "many"
    if token == "们":
        return "plural"
    if token in NEGATIONS:
        return "neg"
    if token in QUESTION_PARTICLES:
        return "qparticle"
    if token in PERF:
        return "perf"
    if token in FUT:
        return "fut"
    if token in WANT:
        return "want"
    if token in COPULA:
        return "copula"
    if token in PREPS:
        return "prep"
    if token in PARTNER:
        return "partner"
    if token in MEASURE or token in STOP:
        return "stop"
    if token in INTENS and token != "好":
        return "intensity"
    word = lexicon.lookup_base(token)
    if word is None:
        return "unknown"
    return {
        "pron": "noun", "n": "noun", "q": "q", "v": "verb",
        "stative": "stative", "time": "time",
    }.get(word.pos, "stop")


def detect_emotion(text: str, punct: str, is_question: bool = False) -> str:
    if any(word in text for word in ("危险", "救命", "小心", "快跑", "别")):
        return "alarm"
    if punct == "!":
        return "excited"
    if is_question:
        return "question"
    if any(word in text for word in ("喜欢", "爱", "谢谢", "抱", "亲", "乖", "晚安")):
        return "soft"
    return "neutral"


def _duck(zh: str | None, lexicon: Lexicon) -> str | None:
    word = lexicon.lookup_base(zh) if zh else None
    return word.duck if word else None


def parse_clause(text: str, punctuation: str, lexicon: Lexicon) -> Frame:
    tokens = tokenize(text, lexicon)
    frame = Frame(source=text, punctuation=punctuation or "。")
    if not tokens:
        frame.kind = "empty"
        return frame

    tagged = [(token, classify(token, lexicon)) for token in tokens]
    question = "yesno" if punctuation in "?？" else None
    pending_place = False
    pending_partner = False
    pending_mods: list[str] = []
    copula = False

    def next_role(i: int) -> str | None:
        j = i + 1
        while j < len(tagged) and tagged[j][1] in {"stop", "intensity"} and tagged[j][0] != "的":
            j += 1
        if j < len(tagged) and tagged[j][0] == "的":
            return "de"
        return tagged[j][1] if j < len(tagged) else None

    last_np: list[NounPhrase] = []

    def add_np(head: str) -> None:
        nonlocal pending_place, pending_partner, pending_mods
        np = NounPhrase(head, pending_mods)
        pending_mods = []
        last_np[:] = [np]
        if pending_place:
            frame.place = np
            pending_place = False
        elif pending_partner:
            frame.partner = np
            pending_partner = False
        elif not frame.verbs and frame.subject is None and not copula:
            frame.subject = np
        elif frame.verbs and _duck(frame.verbs[-1], lexicon) in GO_VERBS and frame.place is None:
            frame.place = np
        else:
            frame.objects.append(np)

    for i, (token, role) in enumerate(tagged):
        nxt = next_role(i)
        if role == "time":
            frame.time = token
        elif role == "noun":
            add_np(token)
        elif role == "q":
            question = "wh"
            add_np(token)
        elif role == "unknown":
            frame.unknown.append(token)
            add_np(token)
        elif role == "one":
            pass
        elif role == "many":
            pending_mods.append("多")
        elif role == "plural":
            if last_np and "多" not in last_np[0].modifiers:
                last_np[0].modifiers.append("多")
        elif role == "neg":
            frame.negation = True
            if token in {"没", "没有"}:
                if nxt in {"verb", "want"}:
                    frame.aspect = "perf"
                elif token == "没有":
                    frame.verbs.append("有")
        elif role == "qparticle":
            question = question or "yesno"
        elif role == "perf":
            frame.aspect = "perf"
        elif role == "fut":
            frame.aspect = "fut"
        elif role == "want":
            following = tagged[i + 1][0] if i + 1 < len(tagged) else None
            if following in WEATHER:
                frame.aspect = "fut"
            else:
                frame.verbs.append(token)
        elif role == "copula":
            copula = True
        elif role == "prep":
            if nxt in {"noun", "q", "unknown"}:
                pending_place = True
        elif role == "partner":
            if frame.subject is not None and not frame.verbs:
                pending_partner = True
        elif role == "intensity":
            frame.intensity = max(frame.intensity, 2 if token in STRONG_INTENS else 1)
        elif role == "verb":
            frame.verbs.append(token)
        elif role == "stative":
            if token == "好" and nxt == "stative":
                frame.intensity = max(frame.intensity, 1)
            elif nxt in {"de", "noun", "unknown"} and not (nxt == "de" and i + 2 >= len(tagged)):
                pending_mods.append(token)
            elif nxt in {"verb", "want"} and frame.manner is None:
                frame.manner = token
            elif frame.verbs and frame.objects:
                frame.objects[-1].modifiers.append(token)
            elif frame.predicate is None:
                frame.predicate = token
            else:
                frame.dropped.append(token)
        # stop 词直接吞掉

    if pending_mods:
        if frame.predicate is None and not frame.verbs:
            frame.predicate = pending_mods.pop(0)
        frame.dropped.extend(pending_mods)

    # "是" 后面只有形容词：天空是蓝的 -> 形容词谓语
    if copula and frame.predicate is None and frame.objects:
        frame.verbs.append("是")
    frame.question = question

    if frame.verbs:
        frame.kind = "verbal"
    elif frame.predicate is not None:
        frame.kind = "stative"
        if frame.aspect == "perf":
            frame.aspect = None  # 状态变化的"了"不译
    elif frame.place is not None:
        frame.kind = "locative"
    elif frame.subject is not None or frame.objects:
        frame.kind = "nominal"
    else:
        frame.kind = "empty" if not frame.time else "nominal"

    frame.emotion = detect_emotion(text, punctuation, question is not None)
    return frame
