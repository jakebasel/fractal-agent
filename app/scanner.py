"""Chart scanner: setups the engine never flags (reversal set ups, 1m plays, zone plays).

Every SCAN_MINUTES inside SCAN_WINDOWS (ET), if there is a fresh screenshot set the vision
model has not read yet and today's spend is under budget, the chart read goes to the decision
model with one question: is a rulebook play forming or ready that fvg-mcp has not armed?
Findings are logged (table `scans`), never traded. Cost ~ $0.003 per scan.
"""
import json
import logging
from datetime import datetime, timezone

from . import config, llm, prompts, store
from .mcp_client import FVG

log = logging.getLogger("scanner")
_last = {"at": 0.0, "files": None}


def _windows():
    out = []
    for w in config.SCAN_WINDOWS.split(","):
        w = w.strip()
        if "-" not in w:
            continue
        a, b = w.split("-")
        out.append(((int(a[:2]), int(a[3:5])), (int(b[:2]), int(b[3:5]))))
    return out


def in_window(now: datetime) -> bool:
    et = now.astimezone(config.ET)
    if et.weekday() == 5 or (et.weekday() == 6 and et.hour < 18):
        return False
    hm = (et.hour, et.minute)
    return any(a <= hm < b for a, b in _windows())


def due(now: datetime, files) -> bool:
    if config.SCAN_MINUTES <= 0 or not files or not in_window(now):
        return False
    if files == _last["files"]:
        return False
    return now.timestamp() - _last["at"] >= config.SCAN_MINUTES * 60


def scan(fvg: FVG, chart_read, files, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    if not chart_read or not due(now, files) or store.over_budget():
        return None
    _last.update(at=now.timestamp(), files=files)
    armed = {}
    for sym in config.SYMBOLS:
        try:
            armed[sym] = [{k: x.get(k) for k in ("cascade", "direction", "mt", "mt_tf", "status", "stage")}
                          for x in (fvg.setups(sym) or {}).get("setups", []) or []]
        except Exception as e:   # the scanner is optional: never raise into the loop
            armed[sym] = f"unavailable: {e}"[:100]
    try:
        res = llm.decide(prompts.scan_system(), prompts.scan_user(chart_read, armed, now), purpose="scan")
    except Exception as e:
        log.warning("scan failed: %s", e)
        return None
    found = res.get("setups") or []
    for f in found:
        store.add_scan(now.isoformat(), files, f.get("symbol"), f.get("play"), f.get("direction"),
                       f.get("stage"), f.get("entry"), f.get("stop"), f.get("target"),
                       f.get("confidence"), f.get("reasons"), f.get("engine_has_it"))
    log.info("scan: %d setup(s) spotted", len(found))
    return found


# ---- scoring spotted setups from the price archive (no model calls) ---------------------------

def replay(ticks, direction: str, entry: float, stop: float, target: float, start_ms: int,
           max_h: float = 2.0, kills=None):
    """fvg-mcp's management on a price tape: at 2R take 50% and move the stop to breakeven,
    runner to the 1:3 target. `kills` = times (ms) of a 5m DB against the trade: the
    instructor's rule is to close (or roll) there, so the trade is closed at that tick.
    Returns (R, outcome) or (None, reason) if the tape can't decide."""
    bull = direction == "bull"
    kills = sorted(kills or [])
    risk = (entry - stop) if bull else (stop - entry)
    if risk <= 0:
        return None, "bad levels"
    two_r = entry + 2 * risk if bull else entry - 2 * risk
    filled, half, last = False, False, None
    end_ms = start_ms + max_h * 3600_000
    for ms, px in ticks:
        if ms < start_ms:
            continue
        if ms > end_ms:
            break
        last = px
        if not filled:
            if (px <= entry) if bull else (px >= entry):
                filled = True
            else:
                continue
        hit_stop = (px <= stop) if bull else (px >= stop)
        hit_tgt = (px >= target) if bull else (px <= target)
        hit_2r = (px >= two_r) if bull else (px <= two_r)
        if kills and ms >= kills[0]:
            open_r = ((px - entry) if bull else (entry - px)) / risk
            r = round(1.0 + 0.5 * open_r, 3) if half else round(open_r, 3)
            return r, "closed: 5m DB against the play" + (" (after 2R)" if half else "")
        if not half:
            if hit_stop:
                return -1.0, "stopped (-1R)"
            if hit_2r:
                half, stop = True, entry   # 50% off at 2R, stop to breakeven
        if half:
            if hit_tgt:
                return 2.5, "2R + runner to 3R"
            if (px <= stop) if bull else (px >= stop):
                return 1.0, "2R, runner to BE"
    if not filled:
        return 0.0, "never filled"
    if last is None:
        return None, "no data"
    open_r = ((last - entry) if bull else (entry - last)) / risk
    r = round(1.0 + 0.5 * open_r, 3) if half else round(open_r, 3)
    return r, f"auto-closed {max_h:g}h" + (" (2R + runner)" if half else "")


def score_pending(fvg: FVG, now: datetime | None = None) -> int:
    """Score 'ready' spotted setups older than 2.5h against fvg-mcp's archived price tape."""
    now = now or datetime.now(timezone.utc)
    cutoff = datetime.fromtimestamp(now.timestamp() - 2.5 * 3600, tz=timezone.utc).isoformat()
    done = 0
    for s in store.scans_to_score(cutoff):
        at = datetime.fromisoformat(s["at"])
        try:
            ticks = fvg.archived_prices(s["symbol"], at.strftime("%Y-%m-%d"))
            if at.hour >= 21:   # the 2h window may run into the next UTC day
                ticks = ticks + fvg.archived_prices(
                    s["symbol"], datetime.fromtimestamp(at.timestamp() + 86400, tz=timezone.utc).strftime("%Y-%m-%d"))
        except Exception as e:
            log.warning("archived_prices for scan %s: %s", s["id"], e)
            store.scan_try(s["id"])
            continue
        if not ticks:
            store.scan_try(s["id"])   # archive not there yet: try again later (max 4 tries)
            continue
        r, outcome = replay(ticks, s["direction"], s["entry"], s["stop"], s["target"], int(at.timestamp() * 1000))
        if r is None:
            store.scan_try(s["id"])
            continue
        store.score_scan(s["id"], r, outcome)
        done += 1
    return done


def sanity_check(chart_read, entry: dict) -> tuple[float | None, str]:
    """How much to trust this chart read for this entry: does the vision model's last price
    for the entry's symbol sit within 0.5% of the engine's entry price, and did it read any
    levels at all? Returns (score 0..1 or None if nothing to compare, note)."""
    if not chart_read or not isinstance(chart_read, dict):
        return None, "no read"
    sym = (entry.get("symbol") or "")[:3].upper()
    charts = [c for c in chart_read.get("charts") or [] if (c.get("symbol") or "").upper() == sym]
    if not charts:
        return 0.0, f"{sym} not found on screen"
    price = entry.get("entry")
    reads = [c.get("last_price") for c in charts if isinstance(c.get("last_price"), (int, float))]
    levels = sum(len(c.get("white_lines") or []) + len(c.get("zones") or []) + len(c.get("reversal_zones") or [])
                 for c in charts)
    if not reads or not price:
        return 0.3 if levels else 0.1, f"no price read; {levels} levels"
    diff = min(abs(r - price) / price for r in reads)
    if diff <= 0.005:
        return (1.0 if levels else 0.7), f"price within {diff:.2%}; {levels} levels"
    return 0.2, f"price off by {diff:.1%}; {levels} levels"
