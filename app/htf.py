"""Higher-timeframe fair value gaps computed from fvg-mcp's archived price tape (no vision
model, no LLM). Rule 2.8 (don't enter long deeper into an overhead 4H FVG / short into one
below) and Reversal Set Up criterion 1 (price reached a 4H or daily FVG) need these, and they
are usually off-screen.

The archive holds whole UTC days; the current day is only archived after it ends, so today's
4H candles are missing. The context says how fresh the data is so the model can say "unknown".
"""
import logging
import time
from datetime import datetime, timedelta, timezone

from . import config

log = logging.getLogger("htf")
_cache: dict = {}   # symbol -> {"at": ts, "fvgs": [...], "through": "YYYY-MM-DD"}
TTL_S = 3600
DAYS = 4


def candles(ticks, minutes: int) -> list:
    """OHLC candles of `minutes` from [[ms, price], ...] in arrival order."""
    out, cur = [], None
    size = minutes * 60_000
    for ms, px in ticks:
        b = int(ms // size) * size
        if cur is None or cur["t"] != b:
            if cur:
                out.append(cur)
            cur = {"t": b, "o": px, "h": px, "l": px, "c": px}
        else:
            cur["h"] = max(cur["h"], px)
            cur["l"] = min(cur["l"], px)
            cur["c"] = px
    if cur:
        out.append(cur)
    return out


def fvgs_of(cs: list, tf: str) -> list:
    """Three-candle gaps: bullish when candle 1 high < candle 3 low, bearish when candle 1 low >
    candle 3 high. Marked filled once a later candle trades through the whole gap."""
    out = []
    for i in range(2, len(cs)):
        a, c = cs[i - 2], cs[i]
        if a["h"] < c["l"]:
            out.append({"tf": tf, "dir": "bull", "top": c["l"], "bottom": a["h"], "at_ms": cs[i - 1]["t"], "filled": False})
        elif a["l"] > c["h"]:
            out.append({"tf": tf, "dir": "bear", "top": a["l"], "bottom": c["h"], "at_ms": cs[i - 1]["t"], "filled": False})
    for g in out:
        later = [x for x in cs if x["t"] > g["at_ms"] + (cs[1]["t"] - cs[0]["t"] if len(cs) > 1 else 0)]
        g["filled"] = any((x["l"] <= g["bottom"] if g["dir"] == "bull" else x["h"] >= g["top"]) for x in later)
    return out


def _fetch(fvg, symbol: str):
    ticks, through = [], None
    today = datetime.now(timezone.utc).date()
    for d in range(DAYS, -1, -1):
        day = (today - timedelta(days=d)).strftime("%Y-%m-%d")
        try:
            t = fvg.archived_prices(symbol, day)
        except Exception as e:
            log.warning("archived_prices %s %s: %s", symbol, day, e)
            t = []
        if t:
            ticks.extend(t)
            through = day
    return ticks, through


def htf_fvgs(fvg, symbol: str) -> dict:
    """{"4h": [...open gaps...], "1d": [...], "through": day, "age_h": hours since the last tick}"""
    c = _cache.get(symbol)
    if c and time.time() - c["at"] < TTL_S:
        return c["out"]
    ticks, through = _fetch(fvg, symbol)
    if not ticks:
        out = {"4h": [], "1d": [], "through": None, "age_h": None, "note": "no archived prices"}
    else:
        c4, c1d = candles(ticks, 240), candles(ticks, 1440)
        last_ms = ticks[-1][0]
        out = {
            "4h": [{k: v for k, v in g.items() if k != "filled"} | {"at_et": _et(g["at_ms"])}
                   for g in fvgs_of(c4, "4h") if not g["filled"]][-8:],
            "1d": [{k: v for k, v in g.items() if k != "filled"} | {"at_et": _et(g["at_ms"])}
                   for g in fvgs_of(c1d, "1d") if not g["filled"]][-4:],
            "through": through, "age_h": round((time.time() * 1000 - last_ms) / 3600_000, 1),
            "note": "from fvg-mcp's archived tape; today's candles are missing until the day is archived",
        }
    _cache[symbol] = {"at": time.time(), "out": out}
    return out


def _et(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(config.ET).strftime("%a %m-%d %H:%M ET")


def relation(price: float, gaps: list) -> list:
    """Where the price sits relative to each open gap: inside / above / below, with distance."""
    out = []
    for g in gaps:
        if g["bottom"] <= price <= g["top"]:
            rel = "inside"
        elif price > g["top"]:
            rel = f"above by {round(price - g['top'], 2)}"
        else:
            rel = f"below by {round(g['bottom'] - price, 2)}"
        out.append({**g, "price_is": rel})
    return out


def rule_2_8(direction: str, entry: float, gaps4h: list) -> str | None:
    """Long inside a bearish 4H FVG (overhead supply) or short inside a bullish one."""
    for g in gaps4h:
        inside = g["bottom"] <= entry <= g["top"]
        if inside and ((direction == "bull" and g["dir"] == "bear") or (direction == "bear" and g["dir"] == "bull")):
            return f"§2.8 entering {'long' if direction == 'bull' else 'short'} inside a {g['dir']}ish 4H FVG {g['bottom']}-{g['top']} ({g['at_et']})"
    return None
