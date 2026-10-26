from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Token:
    text: str
    gloss: str
    kind: str = "word"
    emphasis: int = 0


@dataclass
class NounPhrase:
    head: str
    modifiers: list[str] = field(default_factory=list)


@dataclass
class Frame:
    """中文子句的语义框架。所有槽位都存中文词，生成时再查词典。"""

    kind: str = "fragment"
    time: str | None = None
    subject: NounPhrase | None = None
    partner: NounPhrase | None = None
    objects: list[NounPhrase] = field(default_factory=list)
    place: NounPhrase | None = None
    verbs: list[str] = field(default_factory=list)
    manner: str | None = None
    predicate: str | None = None
    negation: bool = False
    aspect: str | None = None
    question: str | None = None
    intensity: int = 0
    unknown: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    source: str = ""
    punctuation: str = "。"
    emotion: str = "neutral"


@dataclass
class Clause:
    source: str
    tokens: list[Token]
    punctuation: str = "。"
    emotion: str = "neutral"

    @property
    def words(self) -> list[str]:
        return [part for token in self.tokens for part in token.text.split()]

    @property
    def duck(self) -> str:
        text = " ".join(token.text for token in self.tokens if token.text).strip()
        if not text:
            return ""
        if self.punctuation in "。！？!?,":
            return text + self.punctuation
        return text

    @property
    def gloss(self) -> str:
        return " ".join(token.gloss for token in self.tokens if token.gloss)


@dataclass
class TranslationResult:
    source: str
    clauses: list[Clause]
    warnings: list[str] = field(default_factory=list)

    @property
    def duck(self) -> str:
        return " ".join(clause.duck for clause in self.clauses).strip()

    @property
    def gloss(self) -> str:
        return " / ".join(clause.gloss for clause in self.clauses).strip()

    @property
    def words(self) -> list[str]:
        return [word for clause in self.clauses for word in clause.words]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "duck": self.duck,
            "gloss": self.gloss,
            "warnings": self.warnings,
            "clauses": [
                {
                    "source": clause.source,
                    "duck": clause.duck,
                    "gloss": clause.gloss,
                    "emotion": clause.emotion,
                }
                for clause in self.clauses
            ],
        }
