"""Hard rules that need no judgment, checked in code before any model call (fast, free,
consistent). Each returns the rulebook section that fired, or None.

Rulebook §2: 1 ND, 2 news, 3 window, 6 no/shallow retracement (DB setups).
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config

log = logging.getLogger("rules")

_news = {"at": 0.0, "events": None, "error": None}


def _iso_to_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def news_events() -> list | None:
    """High-impact USD events this week (cached 1h). None if the calendar can't be fetched."""
    if time.time() - _news["at"] < 3600 and _news["events"] is not None:
        return _news["events"]
    try:
        r = httpx.get(config.NEWS_URL, timeout=10, headers={"User-Agent": "fractal-agent"})
        r.raise_for_status()
        evs = []
        for e in r.json():
            if (e.get("country") or "").upper() == "USD" and (e.get("impact") or "").lower() == "high":
                evs.append({"title": e.get("title"), "at": _iso_to_dt(e["date"])})
        _news.update(at=time.time(), events=evs, error=None)
    except Exception as e:   # calendar down must never block the agent
        log.warning("news calendar: %s", e)
        _news.update(at=time.time(), error=str(e)[:200])
        if _news["events"] is None:
            return None
    return _news["events"]


def news_rule(when: datetime) -> tuple[str | None, dict]:
    """(rule that fired or None, what was checked) for rule §2.2."""
    if not config.NEWS_FILTER:
        return None, {"checked": False}
    evs = news_events()
    if evs is None:
        return None, {"checked": False, "error": _news["error"]}
    et = when.astimezone(config.ET)
    today = [e for e in evs if e["at"].astimezone(config.ET).date() == et.date()]
    week = [e for e in evs if e["at"].astimezone(config.ET).isocalendar()[:2] == et.isocalendar()[:2]
            and any(w in (e["title"] or "").lower() for w in config.NEWS_WEEK_WORDS)]
    info = {"checked": True,
            "today": [f'{e["at"].astimezone(config.ET):%H:%M} {e["title"]}' for e in today],
            "week_flags": sorted({e["title"] for e in week})}
    if today:
        return f"§2.2 high-impact USD news today ({today[0]['title']})", info
    if week:
        return f"§2.2 {', '.join(info['week_flags'][:2])} week: demo only", info
    return None, info


def session_losses(at: datetime) -> int:
    """Settled paper TAKEs that lost in the same session block (ET) as `at`. Results settle
    ~2h after entry, so this lags; it still catches the third and fourth loss of a session."""
    from . import store
    et = at.astimezone(config.ET)
    h = et.hour
    # session blocks: Asia 18-02, London 02-09:30, NY 09:30-13, NY PM 13-18
    if h >= 18 or h < 2:
        start = et.replace(hour=18, minute=0, second=0, microsecond=0)
        if h < 2:
            start = start - timedelta(days=1)
    elif h < 9 or (h == 9 and et.minute < 30):
        start = et.replace(hour=2, minute=0, second=0, microsecond=0)
    elif h < 13:
        start = et.replace(hour=9, minute=30, second=0, microsecond=0)
    else:
        start = et.replace(hour=13, minute=0, second=0, microsecond=0)
    rows = store.decisions(limit=200, since_iso=start.astimezone(timezone.utc).isoformat())
    return sum(1 for r in rows if r["decision"] == "TAKE" and r["r"] is not None and r["r"] < 0
               and r["entry_at"] < at.isoformat())


def _is_db(entry: dict, detail: dict) -> bool:
    cfg = (detail.get("mt_cfg") or "").upper()
    text = (entry.get("mt_text") or "").lower()
    return "DB" in cfg or "double break" in text


def _is_2db(entry: dict, detail: dict) -> bool:
    cfg = (detail.get("mt_cfg") or "").upper()
    text = (entry.get("mt_text") or "").upper()
    return "2DB" in cfg or "2DB" in text or "(2DB)" in text


def hard_rules(entry: dict, detail: dict, now: datetime) -> tuple[list[str], dict]:
    """ALL hard rules that fire, most important first (the overarching reason is reported, not
    whichever check happened to run first), plus the news check result (stored on the row).

    Priority (Jake, 2026-10-07): a 2DB is never traded, ND is never traded, news, then
    retracement, then the session window."""
    fired = []
    if _is_2db(entry, detail):
        fired.append("§2.4 2DB: we don't trade 2DBs")
    if detail.get("trend_fallback"):
        fired.append("§2.1 no Market Translator signal (ND / trend-fallback)")
    at = _iso_to_dt(entry["at"])
    news_fired, info = news_rule(at)
    if news_fired:
        fired.append(news_fired)
    if _is_db(entry, detail) and (detail.get("retrace") or "").lower() in ("none", "shallow"):
        fired.append(f"§2.6 DB with {detail.get('retrace')} retracement (runaway / too shallow)")
    losses = session_losses(at)
    if losses >= 2:
        fired.append(f"§2.13 {losses} losses already this session (paper book): stop")
    et = at.astimezone(config.ET)
    hm = (et.hour, et.minute)
    session = (detail.get("session") or "").lower()
    if et.weekday() == 5 or (et.weekday() == 6 and hm < (18, 0)):
        fired.append("§2.3 weekend (futures reopen Sunday 6 PM ET)")
    if session == "newyork" and hm >= (11, 0):
        fired.append("§2.3 NY AM entry after 11:00 ET (late setups are demo only)")
    if session == "london" and (4, 0) <= hm < (20, 0):
        fired.append("§2.3 London: only the first ~2 hours after 2 AM ET")
    if session == "asia" and (hm >= (22, 0) or hm < (2, 0)):
        fired.append("§2.3 Asia: done by 10 PM ET")
    if detail.get("in_window") is False:
        fired.append("§2.3 outside the session window (engine flag)")
    return fired, info


def hard_rule(entry: dict, detail: dict, now: datetime) -> tuple[str | None, dict]:
    """First (most important) hard rule that fires, plus the news info."""
    fired, info = hard_rules(entry, detail, now)
    return (fired[0] if fired else None), info
