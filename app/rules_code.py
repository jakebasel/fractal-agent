"""Hard rules that need no judgment, checked in code before any model call (fast, free,
consistent). Each returns the rulebook section that fired, or None.

Rulebook §2: 1 ND, 2 news, 3 window, 6 no/shallow retracement (DB setups).
"""
import logging
import time
from datetime import datetime

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


def _is_db(entry: dict, detail: dict) -> bool:
    cfg = (detail.get("mt_cfg") or "").upper()
    text = (entry.get("mt_text") or "").lower()
    return "DB" in cfg or "double break" in text


def hard_rule(entry: dict, detail: dict, now: datetime) -> tuple[str | None, dict]:
    """First hard rule that fires, plus the news check result (stored on the row)."""
    if detail.get("trend_fallback"):
        return "§2.1 no Market Translator signal (ND / trend-fallback)", {}
    if detail.get("in_window") is False:
        return "§2.3 outside the session window (engine flag)", {}
    at = _iso_to_dt(entry["at"])
    et = at.astimezone(config.ET)
    hm = (et.hour, et.minute)
    session = (detail.get("session") or "").lower()
    if et.weekday() >= 5:
        return "§2.3 weekend", {}
    if session == "newyork" and hm >= (11, 0):
        return "§2.3 NY entry after 11:00 ET", {}
    if session == "london" and (4, 0) <= hm < (20, 0):
        return "§2.3 London: only the first ~2 hours after 2 AM ET", {}
    if session == "asia" and (22, 0) <= hm:
        return "§2.3 Asia: done by 10 PM ET", {}
    if _is_db(entry, detail) and (detail.get("retrace") or "").lower() in ("none", "shallow"):
        return f"§2.6 DB with {detail.get('retrace')} retracement (runaway / too shallow)", {}
    fired, info = news_rule(at)
    return fired, info
