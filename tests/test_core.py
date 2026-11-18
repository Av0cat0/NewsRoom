from datetime import datetime, timezone

from newsroom.classify import classify, extract_amount_usd
from newsroom.main import load_config
from newsroom.models import Article
from newsroom.scoring import build_signal
from newsroom.storage import Store

CFG = load_config()


def art(title, general=False, cred=1.0, summary=""):
    return Article("t", title, "https://x/" + title[:10], datetime.now(timezone.utc), summary, general, cred)


def test_english_exit():
    assert classify("Google to acquire Israeli cyber startup Wiz for $32 billion")[0] == "exit_acquisition"


def test_hebrew_exit_and_funding():
    assert classify("חברת סייבר ישראלית נרכשת תמורת 500 מיליון דולר")[0] == "exit_acquisition"
    assert classify("הסטארטאפ גייס 40 מיליון דולר בסבב סדרה ב'")[0] == "funding_round"


def test_ipo_and_distress():
    assert classify("Israeli fintech files for IPO on Nasdaq")[0] == "ipo"
    assert classify("Startup lays off 30% of staff")[0] == "distress"


def test_amounts():
    assert extract_amount_usd("raises $40 million") == 40e6
    assert extract_amount_usd("acquired for $1.2 billion") == 1.2e9
    assert extract_amount_usd("גייסה 40 מיליון דולר") == 40e6
    assert extract_amount_usd("no money here") is None


def test_irrelevant_news_ignored():
    assert build_signal(art("Weather forecast: sunny weekend"), CFG) is None


def test_general_news_needs_tech_context():
    assert build_signal(art("רכישת בית בתל אביב", general=True), CFG) is None
    assert build_signal(art("רכישת סטארטאפ סייבר ב-300 מיליון דולר", general=True), CFG) is not None


def test_big_exit_is_instant_and_small_funding_is_not():
    big = build_signal(art("Google to acquire Wiz for $32 billion"), CFG)
    assert big.tier == "instant"
    small = build_signal(art("Startup raises $3 million seed round"), CFG)
    assert small.tier in ("digest", "log")
    assert small.score < big.score


def test_watchlist_lowers_bar():
    s = build_signal(art("Monday.com expands to new market in Japan"), CFG)
    assert s.watchlist_hits and s.tier == "instant"


def test_story_dedupe(tmp_path):
    st = Store(str(tmp_path / "t.db"))
    a1 = art("Google to acquire Wiz for $32 billion")
    s1 = build_signal(a1, CFG)
    st.save(a1, s1)
    st.mark_alerted(a1.uid)
    assert st.is_duplicate_story("Google to acquire Wiz for $32 billion - report", s1.event_type)
    assert not st.is_duplicate_story("Startup X raises Series B", "funding_round")
