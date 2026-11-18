"""TASE Data Hub (datawise.tase.co.il) - public offerings pipeline.

Uses the "Public Offerings-Online" product: upcoming and open offerings published on Maya.
Auth is the `apikey` header (TASE_API_KEY in .env). Offerings are turned into Articles that carry a
preset event type/weight, since the structured data is more reliable than keyword matching.
"""
from __future__ import annotations
import logging
import os

import httpx

from .models import Article

log = logging.getLogger("newsroom.tase")
BASE = "https://datawise.tase.co.il"
MAYA_REPORT = "https://maya.tase.co.il/reports/details/{}"

_disabled: str | None = None


def _get(client: httpx.Client, path: str, lang: str) -> dict:
    r = client.get(BASE + path, timeout=30, headers={
        "apikey": os.environ["TASE_API_KEY"], "accept-language": lang, "User-Agent": "NewsRoom/1.0"})
    r.raise_for_status()
    return r.json()


def classify_upcoming(item: dict) -> tuple[str, float, str]:
    """-> (event_type, weight, kind label) for an upcoming offering."""
    types = {str(s.get("securityType")) for s in item.get("securitiesTypes", [])}
    new = bool(item.get("isTheCompanyNew"))
    equity = "Share" in types
    if new and equity:
        return "ipo", 92, "IPO (new equity company)"
    if equity:
        return "public_offering", 62, "equity offering"
    if new:
        return "public_offering", 40, "new bond company debut"
    return "public_offering", 35, "bond / debt offering"


def upcoming_articles(data: dict, credibility: float) -> list[Article]:
    out = []
    for it in data.get("getUpcomingOfferingData", {}).get("result", []):
        etype, weight, kind = classify_upcoming(it)
        name = it.get("companyName") or "Unknown issuer"
        draft = it.get("draftTitle")
        sec = ", ".join(sorted({str(s.get("securityType")) for s in it.get("securitiesTypes", []) if s.get("securityType")}))
        title = f"TASE upcoming {kind}: {name}" + (f" - {draft}" if draft else "") + (f" [{sec}]" if sec else "")
        url = it.get("linkToProspectus") or MAYA_REPORT.format(it["mayaReportId"])
        out.append(Article("TASE Offerings", title, url, credibility=credibility,
                           preset=(etype, weight, f"TASE pipeline: {kind}. Early look before it prices.")))
    return out


def open_articles(data: dict, credibility: float) -> list[Article]:
    out = []
    for it in data.get("getOpenOfferingData", {}).get("result", []):
        codes = [str(s.get("securityFullTypeCode") or "") for s in it.get("securities", [])]
        equity = any(c.startswith("01") for c in codes)
        new = bool(it.get("isTheCompanyNew"))
        if new and equity:
            etype, weight, kind = "ipo", 96, "IPO (new equity company)"
        elif equity:
            etype, weight, kind = "public_offering", 70, "equity offering"
        else:
            etype, weight, kind = "public_offering", 35, "bond / debt offering"
        name = it.get("issuerName") or "Unknown issuer"
        title = f"TASE OPEN {kind}: {name} - {it.get('offeringType', '')}, closes {str(it.get('offerEndsAt', ''))[:16]}"
        url = it.get("linkToOfferReport") or MAYA_REPORT.format(it.get("offerNumber"))
        out.append(Article("TASE Offerings", title, url, credibility=credibility,
                           preset=(etype, weight, f"Offering is open for bids now ({kind}).")))
    return out


def fetch(src: dict, client: httpx.Client) -> list[Article]:
    global _disabled
    if _disabled:
        return []
    if not os.environ.get("TASE_API_KEY"):
        _disabled = "TASE_API_KEY not set"
        log.warning("TASE offerings disabled: %s", _disabled)
        return []
    lang, cred = src.get("language", "en-US"), src.get("credibility", 1.2)
    try:
        up = _get(client, "/v1/tase-offering/upcoming", lang)
        op = _get(client, "/v1/tase-offering/open", lang)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403, 429):
            _disabled = f"API refused access (HTTP {e.response.status_code})"
            log.warning("TASE offerings disabled for this run: %s - check key/subscription.", _disabled)
            return []
        raise
    return upcoming_articles(up, cred) + open_articles(op, cred)
