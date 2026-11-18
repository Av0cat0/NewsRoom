from __future__ import annotations
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .notify import EmailNotifier
from .scoring import build_signal
from .sources import fetch_all
from .storage import Store

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("newsroom")


def load_config(path: str | None = None) -> dict:
    with open(path or ROOT / "newsroom" / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def in_quiet_hours(cfg: dict) -> bool:
    q = cfg.get("quiet_hours")
    if not q:
        return False
    h = datetime.now().hour
    start, end = q["start"], q["end"]
    return (start <= h or h < end) if start > end else (start <= h < end)


def run_cycle(cfg: dict, store: Store, notifier: EmailNotifier, dry_run: bool = False) -> int:
    """One poll: fetch -> dedupe -> classify -> alert. Returns number of instant alerts sent."""
    bootstrap = store.is_empty() and cfg.get("bootstrap_silent", True)
    max_age = timedelta(hours=cfg.get("max_age_hours", 24))
    cutoff = datetime.now(timezone.utc) - max_age
    sent = 0

    articles = fetch_all(cfg)
    if bootstrap:
        log.info("First run: recording %d existing articles silently (no alerts).", len(articles))

    for a in articles:
        if store.seen(a.uid):
            continue
        sig = build_signal(a, cfg)
        stale = a.published is not None and a.published < cutoff
        if bootstrap or stale or sig is None:
            store.save(a, sig, silent=bootstrap or stale)
            continue
        if sig.tier != "instant":
            store.save(a, sig)
            continue
        if store.is_duplicate_story(a.title, sig.event_type):
            store.save(a, sig, silent=True)  # same story already alerted via another outlet
            continue
        if in_quiet_hours(cfg) and not sig.watchlist_hits:
            sig.tier = "digest"  # hold non-watchlist alerts until the morning digest
            store.save(a, sig)
            continue
        store.save(a, sig)
        try:
            notifier.send_signal(sig)
            if not dry_run:
                store.mark_alerted(a.uid)
            sent += 1
        except Exception:  # noqa: BLE001
            log.exception("Failed to send alert for %s", a.title)
    log.info("Cycle done: %d instant alert(s).", sent)
    return sent


def run_digest(store: Store, notifier: EmailNotifier, dry_run: bool = False) -> None:
    rows = store.pending_digest()
    if not rows:
        log.info("Digest: nothing to send.")
        return
    notifier.send_digest(rows)
    if not dry_run:
        store.mark_digested([r["uid"] for r in rows])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="newsroom")
    ap.add_argument("--once", action="store_true", help="run a single poll and exit")
    ap.add_argument("--digest", action="store_true", help="send the digest now and exit")
    ap.add_argument("--dry-run", action="store_true", help="print emails instead of sending")
    ap.add_argument("--test-notify", action="store_true", help="send a test email and exit")
    ap.add_argument("--config")
    args = ap.parse_args(argv)

    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(ROOT / "newsroom.log", encoding="utf-8")])
    cfg = load_config(args.config)
    notifier = EmailNotifier(cfg, dry_run=args.dry_run)

    if args.test_notify:
        notifier.send_test()
        return 0

    store = Store(str(ROOT / cfg.get("db_path", "newsroom.db")))
    if args.once:
        run_cycle(cfg, store, notifier, args.dry_run)
        return 0
    if args.digest:
        run_digest(store, notifier, args.dry_run)
        return 0

    from apscheduler.schedulers.blocking import BlockingScheduler
    sched = BlockingScheduler(timezone=cfg.get("timezone", "Asia/Jerusalem"))
    sched.add_job(run_cycle, "interval", minutes=cfg.get("poll_minutes", 10), args=[cfg, store, notifier],
                  next_run_time=datetime.now(), max_instances=1, coalesce=True, id="poll")
    sched.add_job(run_digest, "cron", hour=cfg.get("digest_hour", 8), minute=0, args=[store, notifier], id="digest")
    log.info("NewsRoom started: polling every %s min.", cfg.get("poll_minutes", 10))
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
