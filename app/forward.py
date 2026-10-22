"""Paper forward test (Jake 2026-10-21) of the micro setup found by fvg-mcp's
analysis/rule_impact.py: chosen on 8/17-9/15, held up on 9/16-10/20, now run on entries the
study never saw. Mechanical: fvg-mcp's engine entries and its own trade scoring, no LLM.

The setup, frozen (change it and the test restarts, so the name changes with it):
  - MNQ1!, MES1!, MYM1!; Asia, NY and NY PM only; at most 2 trades per session across the three
  - inside the engine's session windows (Asia 8 PM-12 AM, NY 9:30-12, NY PM 1:30-4 ET)
  - no DB with a none / shallow retracement
  - no entry with 3+ gaps invalidated on the way in
  - nothing from a high-impact USD release until 2 hours after it (CPI/PPI included; since
    2026-10-22 that is also the agent's CPI/PPI rule)
  - only the first entry off a signal (engine rule from 2026-10-22, amendment "One entry per
    signal"): not a change to this setup, so the name stays; the two later entries the engine
    still made on 10/21 before it went live are skipped here too
  - 0.75% risk on a $100,000 account, even lots up to 100 micros, $1.60 a micro all-in plus
    1 tick of slippage
Each entry is decided once, when first seen, and the decision is never revisited (one
exception: a take fvg-mcp later flags as a later entry off its signal becomes a skip, and the
entries after it in that session are decided again); its result
fills in when fvg-mcp scores it. Pass mark: an average of 2%+ a week, no month's drawdown
deeper than 5%.
"""
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from . import config, rules_code, store

log = logging.getLogger("forward")
NAME = "micros-4rule-v1"
START = datetime(2026, 10, 21, tzinfo=config.ET)
SYMBOLS = ("MNQ1!", "MES1!", "MYM1!")
SESSIONS = ("asia", "ny", "nypm")
PER_SESSION = 2
ACCOUNT, RISK_PCT, CAP, FEE_RT = 100_000.0, 0.75, 100, 1.60
PV = {"MNQ1!": 2.0, "MES1!": 5.0, "MYM1!": 0.5}
TICK = {"MNQ1!": 0.25, "MES1!": 0.25, "MYM1!": 1.0}
NEWS_AFTER_MIN = 120
EVERY_S = 600
PASS_WEEK_PCT, PASS_MONTH_DD_PCT = 2.0, 5.0
SCORED = ("on_time", "rescored", "fact")


def slot(t: datetime) -> tuple[str, str]:
    """(session, day) on the ET clock, as the study bucketed it: Asia runs 6 PM to 3 AM and is
    keyed by the evening it opened (a 1 AM Tuesday entry is Monday evening's Asia)."""
    t = t.astimezone(config.ET)
    h = t.hour + t.minute / 60
    if h >= 18 or h < 3:
        return "asia", (t - timedelta(hours=6)).date().isoformat()
    if h < 9.5:
        return "london", t.date().isoformat()
    if h < 12:
        return "ny", t.date().isoformat()
    return "nypm", t.date().isoformat()


def _lots(symbol, entry, stop) -> int:
    pts = abs((entry or 0) - (stop or 0))
    if not pts:
        return 0
    n = min(CAP, int(ACCOUNT * RISK_PCT / 100 / (pts * PV[symbol])))
    return n - n % 2


def _news_block(t: datetime) -> str | None:
    evs = rules_code.news_events()
    if evs is None:
        return None
    for e in evs:
        m = (t - e["at"]).total_seconds() / 60
        if 0 <= m <= NEWS_AFTER_MIN:
            return f"{int(m)} min after {e['title']} ({e['at'].astimezone(config.ET):%H:%M} ET)"
    return None


def decide(e: dict, takes_in_slot: int) -> tuple[str, str]:
    """('take', '') or ('skip', why) for one fvg-mcp trade_history row."""
    t = datetime.fromtimestamp(e["entry_bar"] / 1000, timezone.utc)
    ses, _ = slot(t)
    if e.get("nd"):
        return "skip", "no Market Translator signal (ND)"
    if e.get("later_entry"):
        return "skip", "later entry off a signal already traded (one entry per signal)"
    if ses not in SESSIONS:
        return "skip", f"{ses} session"
    if not e.get("in_window"):
        return "skip", "outside the session window"
    if (e.get("sig") or "") in ("DB", "2DB") and (e.get("retrace") or "") in ("none", "shallow"):
        return "skip", f"DB with a {e['retrace']} retracement"
    if (e.get("n_inv") or 0) >= 3:
        return "skip", f"{e['n_inv']} gaps invalidated on the way in"
    news = _news_block(t)
    if news:
        return "skip", news
    if takes_in_slot >= PER_SESSION:
        return "skip", f"{PER_SESSION} trades already this session"
    if _lots(e["symbol"], e.get("entry"), e.get("stop")) < 2:
        return "skip", "stop too wide for 2 micros at this risk"
    return "take", ""


def _net(row: dict) -> float | None:
    if row["r"] is None:
        return None
    pts = abs(row["entry"] - row["stop"])
    return row["r"] * row["lots"] * pts * PV[row["symbol"]] - row["lots"] * (FEE_RT + TICK[row["symbol"]] * PV[row["symbol"]])


def sync(fvg) -> int:
    """Decide every new entry since START, then fill in results. Returns new decisions."""
    start_ms = START.timestamp() * 1000
    rows = []
    for s in SYMBOLS:
        res = fvg.call("trade_history", days=3, symbol=s)
        if isinstance(res, list):
            res = res[0] if res else {}
        cols = res.get("cols") or []
        rows += [dict(zip(cols, r)) for r in res.get("rows") or []]
    rows = sorted((r for r in rows if r.get("symbol") in SYMBOLS and (r.get("entry_bar") or 0) >= start_ms),
                  key=lambda r: (r["entry_bar"], r["id"]))
    c, new = store.db(), 0
    with store._lock:
        for e in rows:
            have = c.execute("SELECT decision FROM forward_trades WHERE entry_id=?", (e["id"],)).fetchone()
            if have is None:
                t = datetime.fromtimestamp(e["entry_bar"] / 1000, timezone.utc)
                ses, day = slot(t)
                taken = c.execute("SELECT COUNT(*) n FROM forward_trades WHERE name=? AND slot_session=? "
                                  "AND slot_day=? AND decision='take'", (NAME, ses, day)).fetchone()["n"]
                dec, why = decide(e, taken)
                lots = _lots(e["symbol"], e.get("entry"), e.get("stop")) if dec == "take" else 0
                c.execute("INSERT INTO forward_trades(entry_id, name, symbol, entry_bar, et, slot_session, slot_day, "
                          "dir, sig, mt_tf, decision, reason, entry, stop, lots, decided_at) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (e["id"], NAME, e["symbol"], e["entry_bar"], t.astimezone(config.ET).strftime("%a %m-%d %H:%M ET"),
                           ses, day, e.get("dir"), e.get("sig"), e.get("mt_tf"), dec, why, e.get("entry"), e.get("stop"),
                           lots, store.now_utc()))
                new += 1
            elif e.get("later_entry") and have["decision"] == "take":
                # decided before fvg-mcp flagged it (10/21, before the 10/22 rule went live)
                c.execute("UPDATE forward_trades SET decision='skip', reason=?, lots=0 WHERE entry_id=?",
                          ("later entry off a signal already traded (one entry per signal)", e["id"]))
                # the take freed its session slot: re-decide the slot's later entries (they come
                # later in this time-ordered pass and are decided again with the slot recounted)
                c.execute("DELETE FROM forward_trades WHERE name=? AND slot_session=(SELECT slot_session FROM "
                          "forward_trades WHERE entry_id=?) AND slot_day=(SELECT slot_day FROM forward_trades "
                          "WHERE entry_id=?) AND entry_bar > ?", (NAME, e["id"], e["id"], e["entry_bar"]))
            if e.get("r") is not None and e.get("scoring") in SCORED:
                c.execute("UPDATE forward_trades SET r=?, outcome=?, scoring=? WHERE entry_id=?",
                          (e["r"], e.get("outcome"), e.get("scoring"), e["id"]))
        for row in c.execute("SELECT * FROM forward_trades WHERE decision='take' AND r IS NOT NULL").fetchall():
            c.execute("UPDATE forward_trades SET net_usd=? WHERE entry_id=?", (_net(dict(row)), row["entry_id"]))
        c.commit()
    store.kv_set("forward_synced_at", store.now_utc())
    if new:
        log.info("forward test: %d new decision(s)", new)
    return new


def sync_if_due(fvg) -> int:
    last = store.kv_get("forward_synced_at")
    if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < EVERY_S:
        return 0
    return sync(fvg)


def report() -> dict:
    """Weekly %, month-to-date %, the worst drawdown inside each month, and the pass mark."""
    rows = [dict(r) for r in store.db().execute(
        "SELECT * FROM forward_trades WHERE name=? ORDER BY entry_bar, entry_id", (NAME,)).fetchall()]
    takes = [r for r in rows if r["decision"] == "take"]
    done = [r for r in takes if r["net_usd"] is not None]
    weeks, months = defaultdict(float), defaultdict(list)
    for r in done:
        t = datetime.fromtimestamp(r["entry_bar"] / 1000, config.ET)
        y, w, _ = t.isocalendar()
        weeks[f"{y}-W{w:02d}"] += r["net_usd"]
        months[t.strftime("%Y-%m")].append(r["net_usd"])
    mon = {}
    for m, v in months.items():
        eq = pk = dd = 0.0
        for x in v:
            eq += x; pk = max(pk, eq); dd = min(dd, eq - pk)
        mon[m] = {"pct": round(100 * eq / ACCOUNT, 2), "dd_pct": round(100 * dd / ACCOUNT, 2), "trades": len(v)}
    risk = ACCOUNT * RISK_PCT / 100
    wk = {k: round(100 * v / ACCOUNT, 2) for k, v in sorted(weeks.items())}
    avg_wk = round(sum(wk.values()) / len(wk), 2) if wk else None
    worst_dd = min((m["dd_pct"] for m in mon.values()), default=0.0)
    now_et = datetime.now(config.ET)
    this_week = f"{now_et.isocalendar()[0]}-W{now_et.isocalendar()[1]:02d}"
    skips = Counter(r["reason"].split(" (")[0] if "min after" not in r["reason"] else "after news"
                    for r in rows if r["decision"] == "skip")
    return {
        "name": NAME, "since": START.date().isoformat(), "risk_pct": RISK_PCT, "account": ACCOUNT,
        "setup": __doc__.split("The setup, frozen")[1].split("Each entry")[0].strip(),
        "entries_seen": len(rows), "taken": len(takes), "scored": len(done), "open": len(takes) - len(done),
        "win_pct": round(100 * sum(r["r"] > 0 for r in done) / len(done), 1) if done else None,
        "net_r_per_trade": round(sum(r["net_usd"] for r in done) / len(done) / risk, 3) if done else None,
        "total_pct": round(100 * sum(r["net_usd"] for r in done) / ACCOUNT, 2),
        "weeks_pct": wk, "this_week_pct": wk.get(this_week, 0.0), "avg_week_pct": avg_wk,
        "months": mon, "worst_month_dd_pct": worst_dd,
        "pass": {"avg_week_ge_2pct": avg_wk is not None and avg_wk >= PASS_WEEK_PCT,
                 "month_dd_within_5pct": worst_dd >= -PASS_MONTH_DD_PCT},
        "skips": dict(skips.most_common()),
        "last_trades": [{k: r[k] for k in ("et", "symbol", "dir", "sig", "slot_session", "lots", "r", "outcome", "net_usd")}
                        for r in takes[-8:]],
    }


def report_text(rep: dict | None = None) -> str:
    rep = rep or report()
    m = datetime.now(config.ET).strftime("%Y-%m")
    mo = rep["months"].get(m, {"pct": 0.0, "dd_pct": 0.0})
    ok = lambda b: "✓" if b else "✗"
    lines = [f"Forward test {rep['name']} (micros, since {rep['since']}, {rep['risk_pct']}% risk)",
             f"This week: {rep['this_week_pct']:+.2f}%   Month so far: {mo['pct']:+.2f}% (drawdown {mo['dd_pct']:.2f}%)",
             f"Since start: {rep['total_pct']:+.2f}% over {rep['scored']} trades"
             + (f", {rep['win_pct']:.0f}% wins, {rep['net_r_per_trade']:+.2f}R net each" if rep["scored"] else "")
             + (f", {rep['open']} still open" if rep["open"] else ""),
             f"Pass mark: avg week ≥ 2% {ok(rep['pass']['avg_week_ge_2pct'])} "
             f"({rep['avg_week_pct'] if rep['avg_week_pct'] is not None else '–'}%), "
             f"month drawdown ≤ 5% {ok(rep['pass']['month_dd_within_5pct'])} ({rep['worst_month_dd_pct']:.2f}%)"]
    if rep["weeks_pct"]:
        lines.append("Weeks: " + "  ".join(f"{k[-3:]} {v:+.1f}%" for k, v in rep["weeks_pct"].items()))
    if rep["skips"]:
        lines.append("Skipped: " + ", ".join(f"{k} {v}" for k, v in list(rep["skips"].items())[:6]))
    return "\n".join(lines)


def maybe_report(now: datetime | None = None) -> bool:
    """Friday after 4:30 PM ET (or the weekend, if Friday was missed): one Telegram report a week."""
    now = (now or datetime.now(timezone.utc)).astimezone(config.ET)
    if now.weekday() < 4 or (now.weekday() == 4 and (now.hour, now.minute) < (16, 30)):
        return False
    key = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
    if store.kv_get("forward_report_week") == key or not (config.TELEGRAM_PUSH and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return False
    from . import telegram_bot
    telegram_bot.send(config.TELEGRAM_CHAT_ID, report_text())
    store.kv_set("forward_report_week", key)
    return True
