from __future__ import annotations
import math
from datetime import datetime, timezone

from .classify import classify, extract_amount_usd, is_tech_relevant
from .models import Article, Signal


def _amount_factor(amount: float | None) -> float:
    if not amount:
        return 1.0
    # $1M -> 1.0, $10M -> 1.15, $100M -> 1.3, $1B -> 1.45 (capped)
    return min(1.6, 1.0 + 0.15 * max(0.0, math.log10(amount / 1e6)))


def _recency_factor(pub: datetime | None) -> float:
    if pub is None:
        return 1.0
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
    if hours <= 3:
        return 1.1
    if hours <= 24:
        return 1.0
    return max(0.5, 1.0 - (hours - 24) / 96)


def build_signal(a: Article, cfg: dict) -> Signal | None:
    text = a.text
    amount: float | None = None
    matched: list[str] = []
    if a.preset:
        # Structured source (e.g. TASE offerings): the event is already known.
        etype, base, why = a.preset
    else:
        if a.general_news and not is_tech_relevant(text):
            return None
        # The headline is the reliable part; summaries often mention unrelated deals and numbers.
        res = classify(a.title)
        if res:
            amount = extract_amount_usd(a.title)
        else:
            res = classify(text)
            if not res:
                return None
            res = (res[0], res[1] * 0.85, res[2], res[3])  # summary-only match: lower confidence
        etype, base, why, matched = res

    watch_hits = [w for w in cfg.get("watchlist", []) if w and w.lower() in text.lower()]
    boost = 1.0 + 0.25 * min(len(watch_hits), 2)
    ev_mult = cfg.get("event_weights", {}).get(etype, 1.0)

    score = base * ev_mult * _amount_factor(amount) * a.credibility * _recency_factor(a.published) * boost
    score = round(min(score, 150), 1)

    th = cfg.get("thresholds", {})
    if score >= th.get("instant", 85) or (watch_hits and score >= th.get("watchlist_instant", 50)):
        tier = "instant"
    elif score >= th.get("digest", 50):
        tier = "digest"
    else:
        tier = "log"
    return Signal(a, etype, score, tier, amount, matched, watch_hits, why)
