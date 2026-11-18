from __future__ import annotations
import html
import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from .models import Signal

log = logging.getLogger("newsroom.notify")

LABELS = {
    "exit_acquisition": "EXIT/M&A", "ipo": "IPO", "public_offering": "TASE OFFERING", "funding_round": "FUNDING", "market_entry": "MARKET ENTRY",
    "phase_change": "PHASE CHANGE", "distress": "DISTRESS", "vc_fund": "VC FUND",
}


def _money(v):
    if not v:
        return ""
    return f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.0f}M"


class EmailNotifier:
    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run

    def _send(self, msg: EmailMessage) -> None:
        if self.dry_run:
            log.info("[dry-run] would email: %s", msg["Subject"])
            print(f"\n--- EMAIL (dry-run) ---\nSubject: {msg['Subject']}\n{msg.get_body(('plain',)).get_content()}")
            return
        host = os.environ["SMTP_HOST"]
        port = int(os.environ.get("SMTP_PORT", "587"))
        user = os.environ["SMTP_USER"]
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, os.environ["SMTP_APP_PASSWORD"])
            s.send_message(msg)

    def _msg(self, subject: str, text: str, body_html: str) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = subject
        # Gmail only sends as the authenticated account; the display name is what we can control.
        msg["From"] = formataddr((os.environ.get("MAIL_FROM_NAME", "NewsRoom"),
                                  os.environ.get("SMTP_USER", "newsroom@localhost")))
        msg["To"] = os.environ.get("MAIL_TO", os.environ.get("SMTP_USER", ""))
        msg.set_content(text)
        msg.add_alternative(f'<div dir="auto" style="font-family:Segoe UI,Arial,sans-serif">{body_html}</div>', subtype="html")
        return msg

    def send_signal(self, s: Signal) -> None:
        a = s.article
        label = LABELS.get(s.event_type, s.event_type)
        amt = _money(s.amount_usd)
        subject = f"[{label}] {a.title[:110]}" + (f" ({amt})" if amt else "")
        watch = f"Watchlist: {', '.join(s.watchlist_hits)}" if s.watchlist_hits else ""
        text = (f"{a.title}\n\nEvent: {label}   Score: {s.score}   Source: {a.source}\n"
                f"{('Amount: ' + amt) if amt else ''}\n{watch}\nWhy it matters: {s.why}\n\n{a.url}\n")
        body = (f"<h3 style='margin:0 0 8px'>{html.escape(a.title)}</h3>"
                f"<p><b>{label}</b> &middot; score {s.score} &middot; {html.escape(a.source)}"
                f"{' &middot; <b>' + amt + '</b>' if amt else ''}"
                f"{' &middot; <b>' + html.escape(watch) + '</b>' if watch else ''}</p>"
                f"<p><i>{html.escape(s.why)}</i></p><p><a href='{html.escape(a.url)}'>Read the article</a></p>")
        self._send(self._msg(subject, text, body))

    def send_digest(self, rows) -> None:
        if not rows:
            return
        lines, items = [], []
        for r in rows:
            label = LABELS.get(r["event_type"], r["event_type"])
            lines.append(f"[{label} {r['score']}] {r['title']}\n  {r['source']} - {r['url']}")
            items.append(f"<li><b>{label}</b> ({r['score']}) <a href='{html.escape(r['url'])}'>{html.escape(r['title'])}</a>"
                         f" <small>- {html.escape(r['source'])}</small></li>")
        self._send(self._msg(f"NewsRoom daily digest - {len(rows)} signals", "\n\n".join(lines),
                             f"<h3>Daily digest</h3><ul>{''.join(items)}</ul>"))

    def send_test(self) -> None:
        self._send(self._msg("NewsRoom test email", "NewsRoom email delivery works.", "<p>NewsRoom email delivery works.</p>"))
