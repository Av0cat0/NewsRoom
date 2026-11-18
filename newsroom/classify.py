"""Rule-based Hebrew + English event classifier."""
from __future__ import annotations
import re

# event_type -> (base weight, why-it-matters, regex list)
EVENTS: dict[str, tuple[int, str, list[str]]] = {
    "exit_acquisition": (90, "Exit / M&A: valuation event, possible liquidity or a re-rating of peers.", [
        r"\bacqui(?:re|res|red|sition|ring)\b", r"\bto be acquired\b", r"\bbuys?\b.{0,40}\b(?:startup|company)\b",
        r"\bmerger\b", r"\bmerge[sd]?\b", r"\bexit\b", r"\btakeover\b", r"\bbought (?:by|for)\b",
        r"אקזיט", r"רוכש(?:ת|ים)?\s+(?:את\s+)?ה?(?:סטארט|סטרט|חברת|חברה|מפתחת|יצרנית)", r"רכישת\s+(?:ה)?(?:סטארט|סטרט|חברת|חברה)",
        r"נרכש(?:ת|ה)?\b", r"מיזוג", r"השתלטות", r"הצעת רכש", r"מכירת החברה",
    ]),
    "ipo": (85, "IPO / listing: entry point into public markets or a pricing benchmark.", [
        r"\bIPO\b", r"\bgoes? public\b", r"\bgoing public\b", r"\bSPAC\b", r"\bNasdaq debut\b",
        r"הנפק(?:ה|ת)\b", r"מנפיקה", r"ספאק", r"רישום למסחר",
    ]),
    "funding_round": (65, "Funding round: signals investor appetite, stage progression and valuation.", [
        r"\braises?\b.{0,30}\$?\d", r"\bsecures?\b.{0,30}\$?\d", r"\bseries [A-F]\b", r"\bseed round\b", r"\bfunding round\b",
        r"\bpre-?seed\b", r"\bgrowth round\b", r"\bunicorn\b", r"\bvaluation\b", r"\braised\b",
        r"גיוס(?:ה)?\b", r"גייס(?:ה|ו)\b", r"סבב(?: גיוס)?\b", r"סדרה [א-ו]'?", r"יוניקורן", r"מגייסת",
    ]),
    "market_entry": (55, "Market entry / expansion: new geography, vertical or major customer.", [
        r"\bexpands?\b", r"\blaunch(?:es|ed)?\b.{0,40}\b(?:in|to)\b", r"\bopens? (?:an? )?(?:office|R&D|center)\b",
        r"\bnew market\b", r"\bstrategic (?:deal|agreement)\b",
        r"כניסה לשוק", r"נכנסת? לשוק", r"מרחיב(?:ה|ים)?", r"פותח(?:ת)? (?:משרד|מרכז)", r"שיתוף פעולה", r"הסכם אסטרטגי",
    ]),
    "phase_change": (50, "Phase change: pivot, profitability, product launch or leadership change.", [
        r"\bpivots?\b", r"\bprofitab", r"\bnew CEO\b", r"\bappoints?\b.{0,20}\b(?:CEO|CFO)\b", r"\bbreak-?even\b",
        r"\brevenue (?:grew|jumps?|doubles?)\b", r"\bARR\b",
        r"פיבוט", r"רווחיות", r"מנכ\"ל חדש", r"ממנה(?:ת)? מנכ", r"הכנסות (?:זינקו|הוכפלו)",
    ]),
    "distress": (60, "Distress: layoffs / shutdown / debt trouble - risk signal or distressed-entry opportunity.", [
        r"\blayoffs?\b", r"\blays? off\b", r"\bshuts? down\b", r"\binsolven", r"\bbankruptcy\b", r"\bwind(?:s|ing)? down\b",
        r"פיטורי(?:ם|ן)", r"מפטר(?:ת|ים)?", r"חדלות פירעון", r"פשיטת רגל", r"הסדר חוב", r"צמצום כוח אדם",
    ]),
    "vc_fund": (45, "VC / fund activity: new dry powder or fund strategy shift in the ecosystem.", [
        r"\bnew fund\b", r"\bcloses? (?:its )?(?:\w+ )?fund\b", r"\bventure capital fund\b", r"\bVC fund\b",
        r"קרן חדשה", r"סוגרת? קרן", r"קרן הון סיכון",
    ]),
}

TECH_HINTS = re.compile(
    r"הייטק|סטארט|סטרט|טכנולוגי|סייבר|בינה מלאכותית|\bAI\b|startup|hi-?tech|high-?tech|cyber|fintech|software|SaaS|"
    r"semiconductor|פינטק|שבבים|unicorn|יוניקורן|ונצ'?ר|venture",
    re.I)

_AMOUNT = re.compile(
    r"(?:\$|US\$|USD\s?)\s?(\d[\d,]*(?:\.\d+)?)\s?(billion|bn|b|million|mn|m|מיליארד|מיליון)?(?![a-z])"
    r"|(\d[\d,]*(?:\.\d+)?)\s?(billion|bn|million|mn|מיליארד|מיליון)\s?(?:dollars?|USD|\$|דולר)", re.I)
_MULT = {"billion": 1e9, "bn": 1e9, "b": 1e9, "מיליארד": 1e9, "million": 1e6, "mn": 1e6, "m": 1e6, "מיליון": 1e6}

_COMPILED = {k: (w, why, [re.compile(p, re.I) for p in pats]) for k, (w, why, pats) in EVENTS.items()}


def extract_amount_usd(text: str) -> float | None:
    best = None
    for m in _AMOUNT.finditer(text):
        num = m.group(1) or m.group(3)
        unit = (m.group(2) or m.group(4) or "").lower()
        try:
            val = float(num.replace(",", ""))
        except ValueError:
            continue
        val *= _MULT.get(unit, 1.0)
        if val >= 1e5 and (best is None or val > best):
            best = val
    return best


def classify(text: str) -> tuple[str, int, str, list[str]] | None:
    """Return (event_type, weight, why, matched snippets) for the strongest event, or None."""
    best = None
    for etype, (weight, why, pats) in _COMPILED.items():
        hits = [m.group(0) for p in pats if (m := p.search(text))]
        if not hits:
            continue
        w = weight + min(len(hits) - 1, 2) * 3  # more distinct hits -> slightly higher confidence
        if best is None or w > best[1]:
            best = (etype, w, why, hits)
    return best


def is_tech_relevant(text: str) -> bool:
    return bool(TECH_HINTS.search(text))
