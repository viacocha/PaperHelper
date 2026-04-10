from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


@dataclass
class CriterionScore:
    id: str
    name: str
    score: float
    max_score: float
    summary: str


@dataclass
class Issue:
    severity: Literal["high", "medium", "low"]
    title: str
    details: str
    suggestion: str
    paragraph_index: int | None = None


@dataclass
class ParagraphReview:
    index: int
    excerpt: str
    strengths: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class StandardMatch:
    standard_id: str
    standard_name: str
    category: Literal["knowledge_area", "performance_domain"]
    confidence: float


@dataclass
class ReviewResult:
    filename: str
    standard: StandardMatch
    total_score: float
    pass_score: float
    pass_probability: Literal["high", "medium", "low"]
    summary: str
    dimensions: list[CriterionScore]
    issues: list[Issue]
    paragraph_reviews: list[ParagraphReview]
    suggested_report_name: str

    def to_dict(self) -> dict:
        return asdict(self)
