"""Spotlight indicator confirmations ("New Break") as the TradingView chart alerts post them
to fvg-mcp (source='spotlight'; MYM1!, MES1!, MNQ1! since 2026-10-23). Exact, no vision read.

The alert message is JSON built from TradingView placeholders:
  {"source":"spotlight","event":"confirm","cond":"New Break","symbol":"MYM1!",
   "exchange":"CBOT_MINI","tf":"5","time":"2026-10-23T00:30:00Z","open":53056,"close":53050,
   "high":53064,"low":53041,"up":"0","dn":"1","ema20":"53096.1","ema50":"53080.6",
   "ema238":"52948.3","text":"Spotlight New Break MYM1! 5"}
`up` / `dn` are the indicator's "New Break Up" / "New Break Dn" shape plots (1 = printed on
this bar), `ema20/50/238` its three EMA lines, `time` the 5m bar's open time (UTC).

An alert created before the 2026-10-23 message fix sent `time` unquoted, so fvg-mcp could not
parse the JSON and stored the whole message as text. `payload` repairs that, so no
confirmation is lost whichever way it was stored. fvg-mcp is read-only from here.
"""
import json
import re
from datetime import datetime, timedelta, timezone

from . import config, store

_UNQUOTED_ISO = re.compile(r'("time"\s*:\s*)(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)')

# Spotlight dealing-range boxes, ET wall clock (course: Asia 7:30-8:25 PM, London 3:00-3:55 AM,
# NY 9:30-10:25 AM). A confirmation is the first 5m body close outside the box AFTER it closes.
BOXES = (("Asia", (19, 30), (20, 25)), ("London", (3, 0), (3, 55)), ("NY", (9, 30), (10, 25)))
SETUP_WINDOW_MIN = 60     # "no setup within one hour after the range forms = pass on that session"


def _loads(text):
    if not isinstance(text, str) or not text.strip().startswith("{"):
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return json.loads(_UNQUOTED_ISO.sub(r'\1"\2"', text))
    except ValueError:
        return None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f          # NaN -> None


def payload(row: dict) -> dict | None:
    """The Spotlight JSON of one fvg-mcp event row, or None for anything else that was posted
    to the spotlight webhook (test pings, a price alert that borrowed the URL)."""
    raw = row.get("raw")
    if isinstance(raw, str):
        raw = _loads(raw)
    d = None
    if isinstance(raw, dict):
        if raw.get("raw_text"):
            d = _loads(raw["raw_text"])
        elif raw.get("cond") or raw.get("event"):
            d = raw
    if d is None:
        d = _loads(row.get("text") or "")
    if not isinstance(d, dict) or d.get("source") != "spotlight" or d.get("event") != "confirm":
        return None
    return d


def bar_time(value) -> datetime | None:
    """`time` as TradingView renders it: ISO UTC ("2026-10-23T00:30:00Z") or epoch ms."""
    if value is None:
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        ms = float(value)
        return datetime.fromtimestamp(ms / 1000 if ms > 1e11 else ms, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def session_of(dt: datetime) -> tuple[str, int | None, bool]:
    """(box name, minutes after that box closed, inside a forming box?) for a bar time.
    The box is the most recent one that had closed; a bar inside a forming box (should not
    happen for a New Break) is labelled with that box and inside=True."""
    et = dt.astimezone(config.ET)
    minute = et.hour * 60 + et.minute
    for name, (sh, sm), (eh, em) in BOXES:
        if sh * 60 + sm <= minute < eh * 60 + em:
            return name, None, True
    best = None
    for name, _start, (eh, em) in BOXES:
        end = et.replace(hour=eh, minute=em, second=0, microsecond=0)
        if end > et:
            end -= timedelta(days=1)
        gap = int((et - end).total_seconds() // 60)
        if best is None or gap < best[1]:
            best = (name, gap)
    return best[0], best[1], False


def confirmation(row: dict) -> dict | None:
    """One fvg-mcp spotlight row -> a flat confirmation record, or None."""
    d = payload(row)
    if d is None:
        return None
    up, dn = _num(d.get("up")), _num(d.get("dn"))
    direction = "bull" if up == 1 else "bear" if dn == 1 else "unknown"
    dt = bar_time(d.get("time"))
    sess, after, inside = session_of(dt) if dt else (None, None, False)
    out = {"symbol": (d.get("symbol") or row.get("symbol") or "").upper(),
           "direction": direction,
           "bar_et": dt.astimezone(config.ET).strftime("%Y-%m-%d %H:%M ET") if dt else None,
           "bar_utc": dt.isoformat() if dt else None,
           "session": sess, "min_after_box": after, "inside_box": inside,
           "in_setup_window": (after is not None and after <= SETUP_WINDOW_MIN) if dt else None,
           "tf": str(d.get("tf") or row.get("tf") or ""),
           "open": _num(d.get("open")), "high": _num(d.get("high")),
           "low": _num(d.get("low")), "close": _num(d.get("close")),
           "ema20": _num(d.get("ema20")), "ema50": _num(d.get("ema50")), "ema238": _num(d.get("ema238")),
           "received_et": store.to_et(row.get("received_at")),
           "stored_as": "fields" if row.get("event") == "confirm" else "text"}
    return out


def confirmations(rows: list, hours: float = 48, symbol: str | None = None) -> list[dict]:
    """Parsed confirmations from fvg-mcp recent_events rows, newest first, within `hours` of
    now (by the bar time), one per (symbol, bar)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    want = symbol.upper() if symbol else None
    seen, out = set(), []
    for r in rows or []:
        c = confirmation(r)
        if not c or (want and c["symbol"] != want):
            continue
        key = (c["symbol"], c["bar_utc"])
        if key in seen:
            continue
        seen.add(key)
        dt = bar_time(c["bar_utc"])
        if dt and dt < cutoff:
            continue
        out.append(c)
    out.sort(key=lambda c: c["bar_utc"] or "", reverse=True)
    return out


def latest_by_symbol(confs: list[dict]) -> dict:
    out = {}
    for c in confs:                      # newest first, so the first seen wins
        out.setdefault(c["symbol"], c)
    return out
