"""Backtest the code rules and candidate tweaks on fvg-mcp's own trade ledger, under the
protocol in tools/backtest_protocol.md (train/holdout split, fixed pass rule, every run logged).

No API calls unless --propose: pure arithmetic on trades fvg-mcp already scored. Chart-dependent
rules (white lines, zones, Spotlight) cannot be tested here; everything the ledger carries can.

  .venv/bin/python tools/backtest.py                   # pulls trade_history(120 days) from fvg-mcp
  .venv/bin/python tools/backtest.py ledger.json       # or from a saved export
  .venv/bin/python tools/backtest.py --propose         # + ask DeepSeek for 5 new tweaks (~1 cent)

Writes reports/backtest_latest.json (dashboard, Backtest tab) and appends every tweak's result to
reports/backtest_log.jsonl. Every table: n, win%, avg R, total R, max drawdown (R), window.

Tweak DSL (what DeepSeek proposes and code evaluates):
  {"name": "...", "if": [{"col": "dow", "op": "==", "val": "Fri"}], "then": "skip" | "half" | "allow"}
  cols: symbol sig mt_tf session retrace dow hour n_inv two_m tap_depth fvg_gaps v_candles
        n_stages cascade dir in_window nd ; ops: == != in not_in < <= > >=
  "allow" = take the trades a code hard rule removed when the condition holds (tests a rule).
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config, store  # noqa: E402

SYMBOLS = ("MNQ1!", "MES1!")
MIN_AFFECTED = 30
COLS = ("symbol", "sig", "mt_tf", "session", "retrace", "dow", "hour", "n_inv", "two_m", "tap_depth",
        "fvg_gaps", "v_candles", "n_stages", "cascade", "dir", "in_window", "nd")

# Standing tweaks: the seed hypotheses plus the questions the first run raised.
TWEAKS = [
    {"name": "no Friday", "if": [{"col": "dow", "op": "==", "val": "Fri"}], "then": "skip"},
    {"name": "NY after 10:30 half size", "if": [{"col": "session", "op": "==", "val": "newyork"},
                                              {"col": "hour", "op": ">=", "val": 10.5}], "then": "half"},
    {"name": "5m signals only", "if": [{"col": "mt_tf", "op": "!=", "val": "5m"}], "then": "skip"},
    {"name": "DB only (no lone M)", "if": [{"col": "sig", "op": "in", "val": ["M", "2M"]}], "then": "skip"},
    {"name": "skip NY PM", "if": [{"col": "session", "op": "==", "val": "nypm"}], "then": "skip"},
    {"name": "deep retrace DBs only", "if": [{"col": "sig", "op": "==", "val": "DB"},
                                            {"col": "retrace", "op": "not_in", "val": ["deep", "deep+fvg"]}], "then": "skip"},
    {"name": "no gaps invalidated on the way", "if": [{"col": "n_inv", "op": ">", "val": 0}], "then": "skip"},
    {"name": "allow ND entries (tests rule 2.1)", "if": [{"col": "nd", "op": "==", "val": True}], "then": "allow"},
    {"name": "allow engine out-of-window (tests 2.3 flag)", "if": [{"col": "in_window", "op": "==", "val": False},
                                                                   {"col": "nd", "op": "==", "val": False}], "then": "allow"},
]


def load(path):
    if path:
        raw = Path(path).read_text()
        return json.loads(raw[raw.find("{"):])
    from app.mcp_client import FVG
    return FVG().call("trade_history", days=120)


def rows_of(d):
    cols = d["cols"]
    out = []
    for r in d["rows"]:
        x = dict(zip(cols, r))
        if x["symbol"] not in SYMBOLS or x["r"] is None or x["scoring"] in ("late", "unscored"):
            continue
        if x["cascade"] == "Gold Strategy":
            continue
        et = datetime.fromtimestamp(x["entry_bar"] / 1000, tz=timezone.utc).astimezone(config.ET)
        x.update(et=et, date=et.strftime("%Y-%m-%d"), dow=et.strftime("%a"), hour=et.hour + et.minute / 60)
        x["rule"] = code_hard_rule(x)
        out.append(x)
    out.sort(key=lambda x: x["entry_bar"])
    return out


def code_hard_rule(x):
    """Mirror of app/rules_code.hard_rules on ledger columns, same priority (news needs a calendar)."""
    hm = (x["et"].hour, x["et"].minute)
    s = (x["session"] or "").lower()
    if x["sig"] == "2DB":
        return "§2.4 2DB"
    if x["nd"]:
        return "§2.1 ND"
    if x["sig"] == "DB" and (x["retrace"] or "") in ("none", "shallow"):
        return f"§2.6 DB retrace {x['retrace']}"
    if x["et"].weekday() >= 5:
        return "§2.3 weekend"
    if s == "newyork" and hm >= (11, 0):
        return "§2.3 NY after 11:00"
    if s == "london" and (4, 0) <= hm < (20, 0):
        return "§2.3 London after first 2h"
    if s == "asia" and hm >= (22, 0):
        return "§2.3 Asia after 10 PM"
    if x["in_window"] is False:
        return "§2.3 outside window (engine)"
    return None


# ---- DSL ---------------------------------------------------------------------------------------

def _cond(x, c):
    if c["col"] not in COLS:
        raise ValueError(f"unknown column {c['col']}")
    v, t = x.get(c["col"]), c["val"]
    op = c["op"]
    try:
        if op == "==": return v == t
        if op == "!=": return v != t
        if op == "in": return v in t
        if op == "not_in": return v not in t
        if v is None: return False
        if op == "<": return v < t
        if op == "<=": return v <= t
        if op == ">": return v > t
        if op == ">=": return v >= t
    except TypeError:
        return False
    raise ValueError(f"unknown op {op}")


def matches(x, tweak):
    return all(_cond(x, c) for c in tweak["if"])


def apply(rows, tweak):
    """(values of R after the tweak, number of trades affected) on the given rows. Base = code rules."""
    vals, affected = [], 0
    for x in rows:
        kept = x["rule"] is None
        hit = matches(x, tweak)
        if tweak["then"] == "allow":
            if not kept and hit:
                vals.append(x["r"]); affected += 1
            elif kept:
                vals.append(x["r"])
        elif kept:
            if hit and tweak["then"] == "skip":
                affected += 1
            elif hit and tweak["then"] == "half":
                vals.append(x["r"] * 0.5); affected += 1
            else:
                vals.append(x["r"])
    return vals, affected


def removed_or_added(rows, tweak):
    kept = [x for x in rows if (x["rule"] is None) == (tweak["then"] != "allow") and matches(x, tweak)]
    return store.summarize([x["r"] for x in kept])


def evaluate(tweak, train, hold):
    base_t, base_h = store.summarize([x["r"] for x in train if x["rule"] is None]), \
        store.summarize([x["r"] for x in hold if x["rule"] is None])
    vt, at = apply(train, tweak)
    vh, ah = apply(hold, tweak)
    bt, bh = store.summarize(vt), store.summarize(vh)
    cut_t, cut_h = removed_or_added(train, tweak), removed_or_added(hold, tweak)
    adds = tweak["then"] == "allow"
    checks = {
        "enough_affected_on_train": at >= MIN_AFFECTED,
        "total_r_up_on_train": (bt.get("total_r") or 0) > (base_t.get("total_r") or 0),
        "total_r_up_on_holdout": (bh.get("total_r") or 0) > (base_h.get("total_r") or 0),
        "drawdown_not_deeper": (bt.get("max_dd_r") or 0) >= (base_t.get("max_dd_r") or 0)
                               and (bh.get("max_dd_r") or 0) >= (base_h.get("max_dd_r") or 0),
        ("added_trades_positive_both_halves" if adds else "removed_trades_negative_both_halves"):
            ((cut_t.get("avg_r") or 0) > 0 and (cut_h.get("avg_r") or 0) > 0) if adds else
            ((cut_t.get("avg_r") or 0) < 0 and (cut_h.get("avg_r") or 0) < 0),
    }
    misses = [k for k, v in checks.items() if not v]
    verdict = "PASS" if not misses else ("inconclusive" if len(misses) <= 2 else "fail")
    return {"name": tweak["name"], "tweak": tweak, "affected_train": at, "affected_holdout": ah,
            "train": {"base": base_t, "with_tweak": bt, "delta_total_r": round((bt.get("total_r") or 0) - (base_t.get("total_r") or 0), 2)},
            "holdout": {"base": base_h, "with_tweak": bh, "delta_total_r": round((bh.get("total_r") or 0) - (base_h.get("total_r") or 0), 2)},
            "affected_trades": {"train": cut_t, "holdout": cut_h},
            "checks": checks, "misses": misses, "verdict": verdict}


def by(rows, key):
    g = defaultdict(list)
    for x in rows:
        g[str(key(x))].append(x["r"])
    return sorted([{"group": k, **store.summarize(v)} for k, v in g.items()], key=lambda t: -t["n"])


def propose(report) -> list:
    """Ask the decision model for 5 new tweaks in the DSL (one cheap call). Code evaluates them."""
    from app import llm
    system = ("You propose simple tweaks to a futures strategy's trade filter, for backtesting. "
              "The core strategy stays; a tweak only SKIPs, HALVES or ALLOWs trades based on columns "
              "the ledger carries. Prefer tweaks with a trading rationale (sister-pair, session, "
              "signal quality, retracement), not data-mined ones. Reply with ONE JSON object: "
              '{"tweaks": [ {"name": "...", "rationale": "...", "if": [{"col": ..., "op": ..., "val": ...}], "then": "skip"|"half"|"allow"} ]}'
              f"\nAllowed cols: {COLS}. ops: == != in not_in < <= > >=. 'allow' re-admits trades a code rule removed.")
    user = json.dumps({"books": report["books"], "by_session": report["by_session"], "by_signal": report["by_signal"],
                       "by_retrace": report["by_retrace"], "by_hour_et": report["by_hour_et"],
                       "hard_rules": report["hard_rules"], "already_tested": [t["name"] for t in report["tweaks"]]},
                      indent=0)
    res = llm.decide(system, user, purpose="backtest-propose")
    out = []
    for t in res.get("tweaks") or []:
        if isinstance(t.get("if"), list) and t.get("then") in ("skip", "half", "allow") and t.get("name"):
            out.append(t)
    return out[:5]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    rows = rows_of(load(args[0] if args else None))
    if not rows:
        print("no MNQ/MES rows"); return
    cut_i = int(len(rows) * 0.7)
    cut = rows[cut_i]["date"]
    train, hold = [x for x in rows if x["date"] < cut], [x for x in rows if x["date"] >= cut]
    kept = [x for x in rows if x["rule"] is None]
    fired = defaultdict(list)
    for x in rows:
        if x["rule"]:
            fired[x["rule"]].append(x["r"])
    report = {
        "generated_et": datetime.now(config.ET).strftime("%Y-%m-%d %H:%M ET"),
        "window": f"{rows[0]['date']} to {rows[-1]['date']} ET; train < {cut} ({len(train)}), holdout >= {cut} ({len(hold)})",
        "symbols": list(SYMBOLS), "protocol": "tools/backtest_protocol.md", "cut_date": cut,
        "books": {"core_all_entries": store.summarize([x["r"] for x in rows]),
                  "after_code_hard_rules": store.summarize([x["r"] for x in kept]),
                  "removed_by_code_rules": store.summarize([x["r"] for x in rows if x["rule"]])},
        "hard_rules": [{"rule": k, **store.summarize(v)} for k, v in sorted(fired.items(), key=lambda kv: -len(kv[1]))],
        "by_session": by(kept, lambda x: x["session"]), "by_signal": by(kept, lambda x: x["sig"]),
        "by_signal_tf": by(kept, lambda x: x["mt_tf"]), "by_retrace": by(kept, lambda x: x["retrace"]),
        "by_day_of_week": by(kept, lambda x: x["dow"]),
        "by_hour_et": sorted(by(kept, lambda x: f"{int(x['hour']):02d}"), key=lambda t: t["group"]),
        "by_symbol": by(kept, lambda x: x["symbol"]),
        "by_week": sorted(by(kept, lambda x: x["et"].strftime("%G-W%V")), key=lambda t: t["group"]),
        "tweaks": [],
        "note": "r = fvg-mcp's scored result at full size (2R + runner to 3R). Books after code rules. "
                "A tweak PASSES only if it helps on train AND holdout, does not deepen drawdown, and the "
                "trades it changes have the expected sign on both halves (see protocol). Small n is noise.",
    }
    tweaks = list(TWEAKS)
    if "--propose" in sys.argv:
        try:
            tweaks += propose(report)
        except Exception as e:
            print("propose failed:", e)
    log = ROOT / "reports" / "backtest_log.jsonl"
    log.parent.mkdir(exist_ok=True)
    with log.open("a") as f:
        for t in tweaks:
            try:
                ev = evaluate(t, train, hold)
            except ValueError as e:
                print("bad tweak", t.get("name"), e); continue
            report["tweaks"].append(ev)
            f.write(json.dumps({"at": report["generated_et"], "cut": cut, **{k: ev[k] for k in ("name", "tweak", "verdict", "misses", "train", "holdout")}}, default=str) + "\n")
    report["tweaks"].sort(key=lambda e: (e["verdict"] != "PASS", -(e["train"]["delta_total_r"] + e["holdout"]["delta_total_r"])))
    report["tweaks_tried_total"] = sum(1 for _ in log.open())
    (ROOT / "reports" / "backtest_latest.json").write_text(json.dumps(report, indent=1, default=str))

    print("window:", report["window"])
    print(f"\n{'book':<30}{'n':>6}{'win%':>7}{'avgR':>8}{'totR':>9}{'maxDD':>8}")
    for k, v in report["books"].items():
        print(f"{k:<30}{v['n']:>6}{v['win_pct']:>7}{v['avg_r']:>8}{v['total_r']:>9}{v['max_dd_r']:>8}")
    print(f"\n{'hard rule':<30}{'n':>6}{'win%':>7}{'avgR':>8}{'totR':>9}")
    for h in report["hard_rules"]:
        print(f"{h['rule']:<30}{h['n']:>6}{h['win_pct']:>7}{h['avg_r']:>8}{h['total_r']:>9}")
    print(f"\n{'tweak':<40}{'verdict':<13}{'affT':>5}{'dTrain':>8}{'dHold':>8}  misses")
    for e in report["tweaks"]:
        print(f"{e['name'][:39]:<40}{e['verdict']:<13}{e['affected_train']:>5}{e['train']['delta_total_r']:>8}{e['holdout']['delta_total_r']:>8}  {', '.join(e['misses'])}")
    print(f"\ntweaks tried so far (log): {report['tweaks_tried_total']}")


if __name__ == "__main__":
    main()
