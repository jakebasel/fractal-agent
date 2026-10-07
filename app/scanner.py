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
    if et.weekday() == 5:
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
