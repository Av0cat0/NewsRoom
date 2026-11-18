from __future__ import annotations
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from .models import Article, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles(
  uid TEXT PRIMARY KEY, source TEXT, title TEXT, url TEXT, published TEXT, fetched_at TEXT,
  event_type TEXT, score REAL, tier TEXT, amount_usd REAL, watch TEXT, why TEXT,
  alerted_at TEXT, digested_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_fetched ON articles(fetched_at);
"""
_TOK = re.compile(r"\w{3,}", re.UNICODE)


def tokens(title: str) -> set[str]:
    return {t.lower() for t in _TOK.findall(title)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def is_empty(self) -> bool:
        return self.db.execute("SELECT 1 FROM articles LIMIT 1").fetchone() is None

    def seen(self, uid: str) -> bool:
        return self.db.execute("SELECT 1 FROM articles WHERE uid=?", (uid,)).fetchone() is not None

    def save(self, a: Article, sig: Signal | None, silent: bool = False) -> None:
        """Persist an article. silent=True records it as already handled (bootstrap / stale)."""
        self.db.execute(
            "INSERT OR IGNORE INTO articles(uid,source,title,url,published,fetched_at,event_type,score,tier,amount_usd,watch,why,alerted_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.uid, a.source, a.title, a.url, a.published.isoformat() if a.published else None, _now(),
             sig.event_type if sig else None, sig.score if sig else None, sig.tier if sig else None,
             sig.amount_usd if sig else None, ",".join(sig.watchlist_hits) if sig else None,
             sig.why if sig else None, _now() if silent else None))
        self.db.commit()

    def is_duplicate_story(self, title: str, event_type: str, hours: int = 48, threshold: float = 0.55) -> bool:
        """Story clustering: was a very similar headline with the same event already alerted?"""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        mine = tokens(title)
        if not mine:
            return False
        for r in self.db.execute(
                "SELECT title FROM articles WHERE alerted_at IS NOT NULL AND event_type=? AND fetched_at>=?",
                (event_type, since)):
            other = tokens(r["title"])
            if other and len(mine & other) / len(mine | other) >= threshold:
                return True
        return False

    def mark_alerted(self, uid: str) -> None:
        self.db.execute("UPDATE articles SET alerted_at=? WHERE uid=?", (_now(), uid))
        self.db.commit()

    def pending_digest(self, hours: int = 36):
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return self.db.execute(
            "SELECT * FROM articles WHERE tier='digest' AND alerted_at IS NULL AND digested_at IS NULL "
            "AND fetched_at>=? ORDER BY score DESC", (since,)).fetchall()

    def mark_digested(self, uids: list[str]) -> None:
        self.db.executemany("UPDATE articles SET digested_at=? WHERE uid=?", [(_now(), u) for u in uids])
        self.db.commit()
