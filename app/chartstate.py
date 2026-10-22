"""Chart state on a clock (2026-10-22).

The Hub captures both TradingView layouts every 15 s; until now the vision model only read a
set when a decision or a 5-minute scan needed it, and the read was thrown away afterwards. This
reads the newest set every CHART_STATE_MINUTES inside CHART_STATE_WINDOWS (ET) and stores the
structured read (table `chart_state`), so

  - the Telegram bot / MCP `chart_state` tool answer from a stored read (no vision call),
  - app/watch.py can diff one read against the next (a white line closed through, a reversal
    zone tapped) and see the blue / purple / DSD zones that only a chart shows.

The read itself is agent.chart_read_for_now() (cached per screenshot set), with the extended
VISION_PROMPT (zone shade + distance, HTF chips, DSD). Budget-guarded like the scanner.
"""
import json
import logging
from datetime import datetime, timezone

from . import config, store

log = logging.getLogger("chartstate")
_last = {"at": 0.0, "files": None}


def _windows():
    out = []
    for w in config.CHART_STATE_WINDOWS.split(","):
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
    if config.CHART_STATE_MINUTES <= 0 or not files or not in_window(now):
        return False
    if files == _last["files"]:
        return False
    return now.timestamp() - _last["at"] >= config.CHART_STATE_MINUTES * 60


def refresh(force: bool = False):
    """Read the newest screenshot set if due; store and return the read (or None)."""
    from . import agent   # late: agent imports this module
    now = datetime.now(timezone.utc)
    shots = store.latest_screenshot_set()
    files = ",".join(s["file"] for s in shots) if shots else None
    if not files or (not force and not due(now, files)) or store.over_budget():
        return None
    _last.update(at=now.timestamp(), files=files)
    read, files, _age = agent.chart_read_for_now()
    kind = shots[0]["kind"] if "kind" in shots[0].keys() else None
    store.add_chart_state(shots[-1]["received_at"], files, kind, read)
    return read


def _charts(row) -> list:
    try:
        return (json.loads(row["read"]) or {}).get("charts") or []
    except (TypeError, ValueError):
        return []


def panels(symbol: str | None = None, row=None) -> list:
    """The chart panels of the latest stored read (or `row`), for one symbol or all."""
    row = row or store.latest_chart_state()
    if not row:
        return []
    want = config.sym_key(symbol) if symbol else None
    return [c for c in _charts(row) if not want or config.sym_key(c.get("symbol")) == want]


def latest(symbol: str | None = None) -> dict:
    """Stored read for the MCP / Telegram tool: panels + how old the read is."""
    row = store.latest_chart_state()
    if not row:
        return {"error": "no chart read stored yet (chart state runs inside CHART_STATE_WINDOWS ET)"}
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["at"])).total_seconds()
    return {"read_at_et": store.to_et(row["at"]), "captured_et": store.to_et(row["captured_at"]),
            "age_s": int(age), "readability": row["readability"],
            "charts": panels(symbol, row)}


def previous_panels(symbol: str) -> list:
    """The read before the latest one (for diffs)."""
    rows = store.chart_states(2)
    if len(rows) < 2:
        return []
    return panels(symbol, rows[1])
