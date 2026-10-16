"""Per-symbol core-strategy tracker.

fvg-mcp scores every cascade entry on every symbol it receives alerts for (full size, no AI
filter: the mechanical core strategy). `trade_history` returns those rows for the last N days;
this module mirrors them into `core_trades` (every SYMBOLS_SYNC_S seconds, 2-day window; the
first run backfills SYMBOLS_BACKFILL_DAYS) and reports them per symbol so Jake can see which
instruments the core strategy actually pays on, day by day. No LLM calls, no spend.

Only rows whose `scoring` is on_time / rescored / fact count; `late` and `unscored` are shown as
excluded. "Gold Strategy" rows are left out unless INCLUDE_GOLD=1 (Fractal Effects only).
"""
import logging
from datetime import datetime, timedelta, timezone

from . import config, store

log = logging.getLogger("symbols")

SYNC_EVERY_S = int(config._env("SYMBOLS_SYNC_S", "600"))
BACKFILL_DAYS = int(config._env("SYMBOLS_BACKFILL_DAYS", "30"))
GOOD_SCORING = ("on_time", "rescored", "fact")


def sync(fvg, days: float | None = None) -> int:
    """Pull fvg-mcp's trade_history and upsert it. Returns the number of rows received."""
    first = store.kv_get("core_trades_synced_at") is None
    days = days or (BACKFILL_DAYS if first else 2)
    res = fvg.call("trade_history", days=days)
    if isinstance(res, list):
        res = res[0] if res else {}
    cols, rows = res.get("cols") or [], res.get("rows") or []
    n = store.upsert_core_trades(cols, rows)
    store.kv_set("core_trades_synced_at", store.now_utc())
    log.info("core trades synced: %d rows (%s days)", n, days)
    return n


def sync_if_due(fvg) -> int:
    last = store.kv_get("core_trades_synced_at")
    if last:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
        if age < SYNC_EVERY_S:
            return 0
    return sync(fvg)


def _et_day(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(config.ET).strftime("%Y-%m-%d")


_FEATURES = {
    "direction": lambda r: r["dir"],
    "timeframe": lambda r: r["mt_tf"],
    "signal": lambda r: r["sig"],
    "session": lambda r: r["session"],
    "hour_et": lambda r: datetime.fromtimestamp(r["entry_bar"] / 1000, tz=timezone.utc).astimezone(config.ET).strftime("%H"),
    "weekday_et": lambda r: datetime.fromtimestamp(r["entry_bar"] / 1000, tz=timezone.utc).astimezone(config.ET).strftime("%a"),
    "retrace": lambda r: r["retrace"],
    "cascade": lambda r: r["cascade"],
    "signal_sequence": lambda r: r["mt_seq"],
    "in_window": lambda r: r["in_window"],
    "outcome": lambda r: r["outcome"],
}


def _good(rows) -> list:
    return [r for r in rows if r["scoring"] in GOOD_SCORING and r["r"] is not None
            and not r.get("overridden") and not r.get("stale_signal") and r.get("retap_ok") != 0]


def breakdown(symbol: str | None = None, days: float = 14, min_n: int = 5) -> dict:
    """Winners vs losers for the core strategy on one symbol (or all with symbol=None): every
    entry feature (direction, timeframe, signal, session, ET hour, weekday, retracement, cascade,
    signal sequence, in-window) as buckets with n, win%, avg R, total R, max DD, plus each
    bucket's share of the winners vs the losers, and the best/worst buckets with n >= min_n."""
    since_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    rows = sorted(_good(store.core_trades(since_ms)), key=lambda x: x["entry_bar"])
    if symbol:
        want = symbol.strip().upper()
        exact = [r for r in rows if r["symbol"].upper() == want]
        rows = exact or [r for r in rows if r["symbol"].upper().startswith(want.rstrip("!").rstrip("1"))]
    wins = [r for r in rows if r["r"] > 0]
    losses = [r for r in rows if r["r"] < 0]
    features, buckets = {}, []
    for name, key in _FEATURES.items():
        groups: dict[str, list] = {}
        for r in rows:
            k = key(r)
            groups.setdefault("unknown" if k in (None, "") else str(k), []).append(r)
        table = []
        for g, rs in groups.items():
            s = store.summarize([x["r"] for x in rs])
            s.update(value=g, share_of_wins_pct=round(100 * sum(1 for x in rs if x["r"] > 0) / len(wins), 1) if wins else None,
                     share_of_losses_pct=round(100 * sum(1 for x in rs if x["r"] < 0) / len(losses), 1) if losses else None)
            table.append(s)
            if len(rs) >= min_n and name != "outcome":
                buckets.append({"feature": name, **s})
        features[name] = sorted(table, key=lambda x: -x.get("n", 0))
    buckets.sort(key=lambda x: x.get("avg_r", 0))
    return {"symbol": symbol or "all", "symbols_included": sorted({r["symbol"] for r in rows}),
            "window": f"last {days:g} days", "all": store.summarize([r["r"] for r in rows]),
            "worst_buckets": buckets[:8], "best_buckets": buckets[::-1][:8], "features": features,
            "note": "core strategy, full size, same book as symbol_stats. A bucket whose share of losses is "
                    "much higher than its share of wins is a skip candidate; small n is weak evidence."}


def report(days: float = 7, day_columns: int = 7) -> dict:
    """Per symbol: the core book over `days` (n, win%, avg R, total R, max DD), today, and the
    total R of each of the last `day_columns` ET days. Sorted by total R over the window."""
    now = datetime.now(timezone.utc)
    since_ms = int((now - timedelta(days=days)).timestamp() * 1000)
    rows = store.core_trades(since_ms)
    # the same book as fvg-mcp's Analysis tab (Jake 2026-10-08): a trade overridden by a
    # newer same-timeframe signal, entered off a signal older than 6 h, or a later leg that
    # never re-tapped its zone is not core-strategy and is not counted here either.
    good = _good(rows)
    today = datetime.now(config.ET).strftime("%Y-%m-%d")
    day_keys = [(datetime.now(config.ET) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(day_columns)][::-1]
    by_sym: dict[str, list] = {}
    for r in good:
        by_sym.setdefault(r["symbol"], []).append(r)
    out = []
    for sym, rs in by_sym.items():
        rs.sort(key=lambda x: x["entry_bar"])
        per_day = {}
        for r in rs:
            d = _et_day(r["entry_bar"])
            per_day[d] = round(per_day.get(d, 0.0) + r["r"], 2)
        out.append({
            "symbol": sym,
            "window": store.summarize([r["r"] for r in rs]),
            "today": store.summarize([r["r"] for r in rs if _et_day(r["entry_bar"]) == today]),
            "by_day": {d: per_day.get(d, 0.0) for d in day_keys},
            "by_tf": {tf: store.summarize([r["r"] for r in rs if r["mt_tf"] == tf]) for tf in ("1m", "5m")},
            "by_session": {s: store.summarize([r["r"] for r in rs if r["session"] == s])
                           for s in sorted({r["session"] or "?" for r in rs})},
            "excluded": sum(1 for r in rows if r["symbol"] == sym and r not in rs),
        })
    out.sort(key=lambda x: x["window"].get("total_r", 0), reverse=True)
    synced = store.kv_get("core_trades_synced_at")
    return {"window": f"last {days:g} days (since {store.to_et((now - timedelta(days=days)).isoformat())})",
            "days": day_keys, "symbols": out,
            "all": store.summarize([r["r"] for r in sorted(good, key=lambda x: x["entry_bar"])]),
            "excluded_total": len(rows) - len(good),
            "synced_at_et": store.to_et(synced) if synced else None,
            "note": "core strategy = every fvg-mcp cascade entry at full size, no AI filter, no code "
                    "hard rules. Only on_time/rescored/fact scoring counts; late/unscored rows are "
                    "excluded. Entry days are ET."}
