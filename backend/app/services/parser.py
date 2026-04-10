from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docx import Document


@dataclass
class ParsedEssay:
    paragraphs: list[str]
    text: str
    word_count: int
    title: str


def parse_docx(file_path: Path) -> ParsedEssay:
    document = Document(file_path)
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    text = "\n".join(paragraphs)
    title = paragraphs[0][:50] if paragraphs else file_path.stem
    word_count = _count_words(text)
    return ParsedEssay(paragraphs=paragraphs, text=text, word_count=word_count, title=title)


def _count_words(text: str) -> int:
    compact = text.replace(" ", "").replace("\n", "")
    return len(compact)
