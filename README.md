# NewsRoom

Polls Israeli hi-tech news every 10 minutes, scores articles for investment-relevant events
(exit/M&A, IPO, funding, market entry, phase change, distress, VC funds; Hebrew + English) and
emails you. Plain Python process + SQLite, no agents.

## Setup
```powershell
pip install -r requirements.txt
copy .env.example .env        # fill SMTP_USER / SMTP_APP_PASSWORD (Gmail app password) / MAIL_TO
python -m newsroom.main --test-notify    # sends a test email
python -m newsroom.main --once --dry-run # one poll, prints emails instead of sending
python -m newsroom.main                  # run the service (poll every 10 min, digest 08:00)
```
The very first run records existing articles silently so you are not flooded.

## Run forever on Windows
Task Scheduler -> Create Task -> trigger "At log on" -> action:
`powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File "<path>\run_service.ps1"`

## Tuning (newsroom/config.yaml)
- `watchlist`: companies/VCs that get instant alerts at a lower score bar
- `thresholds`, `event_weights`: what counts as instant vs digest vs ignored
- `quiet_hours`: non-watchlist alerts wait for the morning digest
- `sources`: add/remove feeds. Sites that block plain clients are read via Google News RSS.

## TASE offerings (IPO pipeline)
Uses the TASE Data Hub "Public Offerings-Online" product (`datawise.tase.co.il`, `apikey` header, key in `TASE_API_KEY`).
Upcoming and open offerings are polled with the news feeds. A new company with equity (a real IPO) alerts
immediately, follow-on equity offerings go to the daily digest, bond/debt offerings are only logged.
When a prospectus moves from draft to final it is treated as a new event, so you see stage changes.
This product does not carry general Maya filings; the Google News "Maya" feed is a partial stand-in.

## Tests
`python -m pytest -q`

Informational tool only - not financial advice.
