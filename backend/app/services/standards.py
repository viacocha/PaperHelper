from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Standard:
    id: str
    name: str
    category: str
    aliases: list[str]
    keywords: list[str]
    required_processes: list[str]
    required_artifacts: list[str]
    question_points: list[str]


class StandardLibrary:
    def __init__(self, source_path: Path) -> None:
        self._source_path = source_path
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        self.subject = raw["subject"]
        self.version = raw["version"]
        self.total_score = raw["total_score"]
        self.pass_score = raw["pass_score"]
        self.shared = raw["shared"]
        self.standards = [Standard(**item) for item in raw["standards"]]

    def all(self) -> list[Standard]:
        return self.standards

    def find_best_match(self, text: str, preferred_id: str | None = None) -> tuple[Standard, float]:
        lowered = text.lower()

        if preferred_id:
            explicit = next((item for item in self.standards if item.id == preferred_id), None)
            if explicit:
                return explicit, 1.0

        scored: list[tuple[Standard, float]] = []
        for standard in self.standards:
            hits = 0
            for token in standard.aliases + standard.keywords:
                if token.lower() in lowered:
                    hits += 1
            score = hits / max(1, len(standard.keywords))
            scored.append((standard, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        best_standard, confidence = scored[0]
        return best_standard, confidence


def load_standard_library() -> StandardLibrary:
    here = Path(__file__).resolve().parent.parent
    return StandardLibrary(here / "standards" / "library.json")
