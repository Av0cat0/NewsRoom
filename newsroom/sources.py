from __future__ import annotations
import logging
import re
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from .models import Article

log = logging.getLogger("newsroom.sources")
UA = "NewsRoomBot/1.0 (+personal news monitor)"
_TAGS = re.compile(r"<[^>]+>")


def _published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(timegm(t), tz=timezone.utc)
    return None


def fetch_feed(src: dict, client: httpx.Client) -> list[Article]:
    r = client.get(src["url"], headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    out = []
    for e in feed.entries:
        title = _TAGS.sub("", e.get("title", "")).strip()
        link = e.get("link", "").strip()
        if not title or not link:
            continue
        summary = _TAGS.sub(" ", e.get("summary", ""))[:600].strip()
        out.append(Article(
            source=src["name"], title=title, url=link, published=_published(e), summary=summary,
            general_news=src.get("general", False), credibility=src.get("credibility", 1.0)))
    return out


def fetch_all(cfg: dict) -> list[Article]:
    """Fetch every enabled source; one failing source never stops the others."""
    from . import tase

    articles: list[Article] = []
    with httpx.Client() as client:
        for src in cfg["sources"]:
            if not src.get("enabled", True):
                continue
            try:
                if src.get("type") == "tase_offerings":
                    got = tase.fetch(src, client)
                else:
                    got = fetch_feed(src, client)
                log.info("%-22s %3d items", src["name"], len(got))
                articles.extend(got)
            except Exception as exc:  # noqa: BLE001 - isolate per-source failures
                log.warning("%-22s failed: %s", src["name"], exc)
    return articles
