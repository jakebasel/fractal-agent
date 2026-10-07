"""The improvement loop. Nothing here changes the live rules.

  lesson proposal --> hypothesis (deduplicated; support counts how often it was proposed)
  hypothesis "testing" --> shadow decision on every reviewed setup, past (backfill) and future
  settled R --> each hypothesis' book vs the agent and the core strategy on the SAME trades
  Jake approves --> it goes into rules/amendments.md (git), new rules_version from then on

Books:
  core   = every engine entry at full size (the mechanical strategy, what fvg-mcp would do)
  agent  = the AI's paper book (TAKEs, reduced = 0.5)
  H<n>   = the agent with that one change added
"""
import json
import logging
from datetime import datetime, timezone

from . import config, llm, prompts, store

log = logging.getLogger("learning")

# Starting hypotheses: findings from fvg-mcp's own ledger and the rules we most want to test.
SEEDS = [
    ("No Friday trades", "IF the entry is on a Friday (ET) THEN SKIP.", "engine-data",
     "fvg-mcp's ledger analysis removes Friday trades (its rule R5b)."),
    ("News: release day only", "IF the only news concern is a CPI/PPI/FOMC WEEK (no high-impact USD "
     "release today) THEN ignore the news rule and decide normally.", "rules-test",
     "Tests whether the 'demo-only week' part of §2.2 costs more than it saves."),
    ("NY after 10:30 reduced", "IF a New York session entry is after 10:30 ET THEN reduce size "
     "(TAKE becomes reduced; never upgrade a SKIP).", "rules-test",
     "Live sessions: the sweet spot is in by ~10:30-10:40 ET; later setups get reassessed."),
]


def _since(days) -> str:
    return datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - days * 86400,
                                  tz=timezone.utc).isoformat()


def seed():
    if store.kv_get("seeded_hypotheses"):
        return
    for title, rule, source, note in SEEDS:
        store.add_hypothesis(title, rule, None, source, "testing", note=note)
    store.kv_set("seeded_hypotheses", True)


def _open_slots() -> int:
    return config.MAX_TESTING_HYPOTHESES - len(store.hypotheses("testing"))


def register_proposal(lesson: dict, entry_id: int):
    """A lesson's proposal becomes a hypothesis, or adds support to one that says the same."""
    rule = (lesson or {}).get("proposal")
    if not rule or str(rule).strip().lower() in ("null", "none", ""):
        return None
    existing = store.hypotheses(["testing", "queued", "approved", "rejected"])
    title = lesson.get("proposal_title")
    same = None
    if existing:
        try:
            m = llm.decide(prompts.MATCH_SYSTEM, prompts.match_user(rule, existing),
                           purpose="hypothesis")
            same = m.get("same_as")
            title = title or m.get("title")
        except Exception as e:
            log.warning("proposal match failed: %s", e)
    ids = {h["id"] for h in existing}
    if same in ids:
        store.support_hypothesis(same, entry_id)
        # a queued idea that keeps coming back gets a testing slot when one frees up
        return same
    status = "testing" if _open_slots() > 0 else "queued"
    return store.add_hypothesis(title or rule[:40], rule, lesson.get("rule_ref"), "lesson",
                                status, entry_ids=[entry_id])


def promote_queued():
    slots = _open_slots()
    if slots <= 0:
        return
    queued = sorted(store.hypotheses("queued"), key=lambda h: -(h["support"] or 0))
    for h in queued[:slots]:
        store.set_hypothesis_status(h["id"], "testing")


def run_shadow(limit: int | None = None) -> int:
    """Shadow-decide up to `limit` setups for the testing hypotheses (newest first, then
    backfill). One DeepSeek call per setup covers every hypothesis it is missing."""
    if store.over_budget():
        return 0
    testing = {h["id"]: h for h in store.hypotheses("testing")}
    todo = store.shadow_todo(list(testing), _since(config.SHADOW_BACKFILL_DAYS),
                             limit or config.SHADOW_PER_TICK)
    done = 0
    for row, missing in todo:
        hyps = [testing[i] for i in missing]
        try:
            res = llm.decide(prompts.shadow_system(), prompts.shadow_user(row, hyps),
                             purpose="shadow")
        except Exception as e:
            log.warning("shadow %s failed: %s", row["entry_id"], e)
            break   # try again next tick
        for h in hyps:
            a = res.get(str(h["id"])) or res.get(h["id"]) or {}
            d = (a.get("decision") or row["decision"]).upper()
            d = d if d in ("TAKE", "SKIP") else row["decision"]
            size = (a.get("size") or "").lower()
            size = "none" if d == "SKIP" else (size if size in ("full", "reduced") else
                                               (row["size"] if row["size"] in ("full", "reduced") else "reduced"))
            changed = (d, size) != (row["decision"], row["size"])
            store.add_shadow(row["entry_id"], h["id"], d, size, changed, a.get("why"))
        done += 1
    return done


# ---- results -------------------------------------------------------------------------------

def _paper(decision, size, r):
    if r is None or decision != "TAKE":
        return 0.0 if r is not None else None
    return r * store.SIZE_MULT.get(size or "none", 0.0)


def hypothesis_result(h) -> dict:
    rows = [x for x in store.shadows_for(h["id"]) if x["r"] is not None]
    shadow = [_paper(x["decision"], x["size"], x["r"]) for x in rows]
    agent = [_paper(x["real_decision"], x["real_size"], x["r"]) for x in rows]
    core = [x["r"] for x in rows]
    s_book, a_book = store.summarize(shadow), store.summarize(agent)
    delta = round((s_book.get("total_r") or 0) - (a_book.get("total_r") or 0), 2)
    changed = [x for x in rows if x["changed"]]
    n = len(rows)
    if n < config.MIN_N_FOR_VERDICT:
        verdict = f"collecting data ({n}/{config.MIN_N_FOR_VERDICT} settled)"
    elif delta > 0 and (s_book.get("max_dd_r") or 0) >= (a_book.get("max_dd_r") or 0) - 1:
        verdict = "beats the agent: review for approval"
    elif delta > 0:
        verdict = "more R but deeper drawdown: judgment call"
    else:
        verdict = "does not beat the agent"
    return {
        "id": h["id"], "title": h["title"], "rule": h["rule"], "rule_ref": h["rule_ref"],
        "source": h["source"], "status": h["status"], "support": h["support"],
        "created_et": store.to_et(h["created_at"]), "note": h["note"],
        "shadow_evaluated": len(store.shadows_for(h["id"])), "settled": n,
        "decisions_changed": len(changed),
        "books_same_trades": {"with_change": s_book, "agent": a_book,
                              "core": store.summarize(core)},
        "delta_total_r_vs_agent": delta, "verdict": verdict,
    }


def _group(rows, key, value="r"):
    groups = {}
    for r in rows:
        k = key(r)
        if isinstance(k, list):
            for kk in k:
                groups.setdefault(kk, []).append(r[value])
        else:
            groups.setdefault(k if k not in (None, "") else "unknown", []).append(r[value])
    out = [{"group": g, **store.summarize(v)} for g, v in groups.items()]
    return sorted(out, key=lambda x: -x.get("n", 0))


def _jl(x):
    try:
        return json.loads(x) if x else []
    except ValueError:
        return []


def report(days: float = 30) -> dict:
    """Everything in one place. Every table: n, win%, avg R, total R, max drawdown (R)."""
    since = _since(days)
    rows = store.settled(since)
    takes = [r for r in rows if r["decision"] == "TAKE"]
    skips = [r for r in rows if r["decision"] == "SKIP"]
    model_rows = [r for r in rows if r["path"] not in ("code",)]
    verdicts = {}
    for les in store.recent_lessons(100000):
        if les["created_at"] >= since:
            verdicts[les["verdict"]] = verdicts.get(les["verdict"], 0) + 1
    jev_rows = [r for r in rows if r["jev_p_take"] is not None]
    jev_take = [r for r in jev_rows if r["jev_p_take"] >= 0.5]
    agree = sum(1 for r in jev_rows if (r["jev_p_take"] >= 0.5) == (r["decision"] == "TAKE"))
    by_version = {}
    for r in rows:
        by_version.setdefault(r["rules_version"] or "v1", []).append(r)
    return {
        "window": f"last {days:g} days (since {store.to_et(since)})",
        "books": {
            "core_strategy_all_engine_entries": store.summarize([r["r"] for r in rows]),
            "agent_paper_book": store.summarize([r["paper_r"] for r in takes]),
            "agent_takes_full_size": store.summarize([r["r"] for r in takes]),
            "agent_skips_counterfactual": store.summarize([r["r"] for r in skips]),
        },
        "core_by_play": _group(rows, lambda r: r["play"]),
        "agent_by_play": _group(takes, lambda r: r["play"], "paper_r"),
        "core_by_timeframe_signal": _group(rows, lambda r: f"{r['mt_tf'] or '?'} {(r['play'] or '? ?').split(' ')[1] if r['play'] else r['mt_cfg']}"),
        "core_by_timeframe": _group(rows, lambda r: r["mt_tf"]),
        "core_by_session": _group(rows, lambda r: r["session"]),
        "core_by_signal_config": _group(rows, lambda r: r["mt_cfg"]),
        "core_by_grade": _group(model_rows, lambda r: r["grade"]),
        "core_by_booster_present": _group(model_rows, lambda r: _jl(r["boosters"]) or ["(none)"]),
        "hard_rules_skipped_counterfactual": _group(
            [r for r in skips if r["hard_rule"]], lambda r: r["hard_rule"].split(" ")[0]),
        "agent_by_rules_version": [
            {"rules_version": v, **store.summarize([x["paper_r"] for x in rs if x["decision"] == "TAKE"])}
            for v, rs in by_version.items()],
        "lesson_verdicts": verdicts,
        "spotted_by_scanner_book": store.summarize([s["r"] for s in store.scored_scans() if s["at"] >= since]),
        "spotted_by_play": _group([s for s in store.scored_scans() if s["at"] >= since], lambda s: s["play"]),
        "jev": {"mode": config.JEV_MODE, "scored": len(jev_rows),
                "agreement_with_agent_pct": round(100 * agree / len(jev_rows), 1) if jev_rows else None,
                "jev_take_book_full_size": store.summarize([r["r"] for r in jev_take])},
        "hypotheses": [hypothesis_result(h) for h in store.hypotheses(["testing", "queued", "approved"])],
        "spend": store.spend(since),
        "note": "core = mechanical strategy (every engine entry, full size). agent = AI paper book. "
                "Hypotheses are compared on the same settled trades. Small n is noise: wait for "
                f"{config.MIN_N_FOR_VERDICT}+ settled trades before acting on any row.",
    }
