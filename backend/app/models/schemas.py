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
class TopicScorecardItem:
    title: str
    score: float
    max_score: float
    status: Literal["good", "warning", "missing"]
    summary: str


@dataclass
class Issue:
    severity: Literal["high", "medium", "low"]
    action_priority: Literal["must", "should", "could"]
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
class RevisionTemplate:
    title: str
    purpose: str
    when_to_use: str
    outline: list[str]
    sample: str


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
    topic_scorecard: list[TopicScorecardItem]
    issues: list[Issue]
    must_fix: list[Issue]
    should_fix: list[Issue]
    could_improve: list[Issue]
    revision_templates: list[RevisionTemplate]
    paragraph_reviews: list[ParagraphReview]
    suggested_report_name: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompareResult:
    original: ReviewResult
    revised: ReviewResult
    score_delta: float
    pass_probability_changed: bool
    fixed_issues: list[Issue]
    remaining_issues: list[Issue]
    new_issues: list[Issue]
    summary: str
    compare_report_name: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GeneratedPaper:
    title: str
    standard: StandardMatch
    content: str
    paragraphs: list[str]
    word_count: int
    minimum_word_count: int
    generated_report_name: str

    def to_dict(self) -> dict:
        return asdict(self)
