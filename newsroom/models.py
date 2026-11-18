from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    source: str
    title: str
    url: str
    published: datetime | None = None
    summary: str = ""
    general_news: bool = False  # True when the source is not tech-specific
    credibility: float = 1.0
    # (event_type, weight, why) for structured sources that already know what the event is
    preset: tuple[str, float, str] | None = None

    @property
    def uid(self) -> str:
        return hashlib.sha1(f"{self.url}|{self.title}".encode("utf-8")).hexdigest()

    @property
    def text(self) -> str:
        return f"{self.title}. {self.summary}"


@dataclass
class Signal:
    article: Article
    event_type: str
    score: float
    tier: str  # instant | digest | log
    amount_usd: float | None = None
    matched: list[str] = field(default_factory=list)
    watchlist_hits: list[str] = field(default_factory=list)
    why: str = ""
