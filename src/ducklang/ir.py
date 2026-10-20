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
class Frame:
    kind: str = "fragment"
    subject: str | None = None
    subject_parts: list[str] = field(default_factory=list)
    object: str | None = None
    object_parts: list[str] = field(default_factory=list)
    place: str | None = None
    verb: str | None = None
    complement_verb: str | None = None
    adjective: str | None = None
    modifier: str | None = None
    manner: str | None = None
    quantity: str | None = None
    negation: bool = False
    aspect: str | None = None
    modal: str | None = None
    question: str | None = None
    intensity: int = 0
    copula: bool = False
    have: bool = False
    raw: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    source: str = ""
    punctuation: str = "."
    emotion: str = "neutral"


@dataclass
class Clause:
    source: str
    tokens: list[Token]
    punctuation: str = "."
    emotion: str = "neutral"

    @property
    def duck(self) -> str:
        text = " ".join(token.text for token in self.tokens if token.text)
        text = text.strip()
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
