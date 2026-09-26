import json
from pathlib import Path
import re
from typing import Any


class HotelKnowledge:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def public_profile(self) -> dict[str, Any]:
        return {
            "name": self.data.get("name", ""),
            "concierge_name": self.data.get("concierge_name", "Concierge"),
            "welcome": self.data.get("welcome", "How can I help?"),
            "quick_actions": self.data.get("quick_actions", []),
        }

    def retrieve(self, query: str, limit: int = 4) -> list[dict[str, str]]:
        words = {word.lower().strip(".,!?") for word in query.split() if len(word) > 2}
        scored: list[tuple[int, dict[str, str]]] = []

        for item in self.data.get("knowledge", []):
            haystack = " ".join(
                [
                    item.get("title", ""),
                    item.get("answer", ""),
                    " ".join(item.get("keywords", [])),
                ]
            ).lower()
            score = sum(1 for word in words if word in haystack)
            if score:
                scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def exact_fast_answer(self, query: str) -> str | None:
        normalized = query.lower()
        for item in self.data.get("knowledge", []):
            keywords = item.get("keywords", [])
            if any(re.search(rf"(?<!\w){re.escape(keyword.lower())}(?!\w)", normalized) for keyword in keywords if keyword):
                if item.get("fast_path", False):
                    return item["answer"]
        return None
