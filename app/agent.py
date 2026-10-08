"""The review loop: new fvg-mcp entry -> chart read -> DeepSeek decision -> log -> outcome -> lesson.

PAPER ONLY. Nothing here places, modifies or cancels an order.
"""
import json
import logging
import shutil
import threading
import time
from datetime import datetime, timezone

from . import config, htf, jev, knowledge, learning, llm, prompts, rules_code, scanner, store, symbols
from .mcp_client import FVG

log = logging.getLogger("agent")

_vision_cache: dict[str, dict] = {}   # screenshot file -> chart read
_state = {"last_loop": None, "last_error": None, "loops": 0}


# ---- helpers -----------------------------------------------------------------------------

def _iso_to_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _ms_to_iso(ms) -> str | None:
    if ms in (None, ""):
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


def _et(dt: datetime) -> str:
    return dt.astimezone(config.ET).strftime("%a %Y-%m-%d %H:%M:%S ET")


def _detail(entry: dict) -> dict:
    d = entry.get("detail")
    if isinstance(d, str):
        try:
            return json.loads(d)
        except ValueError:
            return {}
    return d or {}


def _summarise_setups(s: dict) -> list:
    out = []
    for x in (s or {}).get("setups", []) or []:
        out.append({k: x.get(k) for k in (
            "cascade", "direction", "mt", "mt_tf", "mt_cfg", "status", "stage", "armed",
            "ready", "retrace", "no_retrace", "two_m", "tf5_db", "conflict", "session",
            "in_window", "high_prob")})
    return out


def _mt_events(fvg: FVG, symbol: str) -> list:
    out = []
    for e in fvg.mt_events(symbol, limit=10):
        try:
            at = _et(_iso_to_dt(e["received_at"]))
        except (KeyError, ValueError, TypeError):
            at = e.get("received_at")
        out.append({"at": at, "tf": e.get("tf"), "text": e.get("text"),
                    "price": e.get("price")})
    return out


def chart_read_for_now():
    """Latest screenshot set (one image per TradingView window), read once by the vision model
    and cached. -> (read|None, files, age_s)"""
    shots = store.latest_screenshot_set()
    if not shots:
        return None, None, None
    files = ",".join(s["file"] for s in shots)
    age = (datetime.now(timezone.utc) - _iso_to_dt(shots[-1]["received_at"])).total_seconds()
    if age > config.SCREENSHOT_MAX_AGE_S:
        return None, files, age
    if files in _vision_cache:
        return _vision_cache[files], files, age
    paths = [config.DATA_DIR / "shots" / s["file"] for s in shots]
    paths = [p for p in paths if p.exists()]
    if not paths:
        return None, files, age
    try:
        kind = shots[0]["kind"] if "kind" in shots[0].keys() else None    # sqlite rows: no .get
        layout = store.kv_get(f"screen_layout:{kind}") if kind else None
        read = llm.read_chart([p.read_bytes() for p in paths], prompts.vision_prompt(layout))
    except Exception as e:
        # cache the failure too: a new screenshot set arrives every 30 s, retrying the same
        # one every 15 s would only burn credits
        log.warning("vision failed for %s: %s", files, e)
        read = None
    if (read or {}).get("readability") == "not_chart":
        read = None   # TradingView wasn't on screen: don't feed a video to the decision
    _vision_cache.clear()
    _vision_cache[files] = read
    return read, files, age


# ---- review ----------------------------------------------------------------------------------

def _base_row(entry: dict, detail: dict) -> dict:
    return {
        "entry_id": entry["id"], "symbol": entry["symbol"], "entry_at": entry["at"],
        "reviewed_at": store.now_utc(), "session": detail.get("session"),
        "cascade": entry.get("cascade"), "direction": entry.get("direction"),
        "mt_text": entry.get("mt_text"), "mt_tf": entry.get("mt_tf"),
        "mt_cfg": detail.get("mt_cfg"), "retrace": detail.get("retrace"),
        "entry": entry.get("entry"), "stop": entry.get("stop"), "target": entry.get("target"),
    }


def build_context(fvg: FVG, entry: dict, detail: dict, chart_read, shot_age) -> dict:
    sym = entry["symbol"]
    pair = config.PAIR.get(sym)
    now = datetime.now(timezone.utc)
    stops = detail.get("stops") or []
    return {
        "now": _et(now),
        "engine": {
            "symbol": sym, "direction": entry.get("direction"), "cascade": entry.get("cascade"),
            "entry": entry.get("entry"), "stop": entry.get("stop"), "target_1to3": entry.get("target"),
            "entry_at": _et(_iso_to_dt(entry["at"])),
            "arming_signal": {"text": entry.get("mt_text"), "tf": entry.get("mt_tf"),
                              "price": entry.get("mt_price"),
                              "at": _et(_iso_to_dt(detail["signal_at"])) if detail.get("signal_at") else None},
            "signal_sequence": [x.get("text") for x in detail.get("mt_seq", [])],
            "config": detail.get("mt_cfg"), "two_m": detail.get("two_m"),
            "retrace_quality": detail.get("retrace"), "tap_depth": detail.get("tap_depth"),
            "fvg_gaps_in_chain": detail.get("fvg_gaps"),
            "gaps_invalidated_on_the_way": len(detail.get("invalidations") or []),
            "stages": [{k: st.get(k) for k in ("tf", "top", "bot", "close_level")}
                       for st in detail.get("stages", [])],
            "stop_options": stops, "session": detail.get("session"),
            "in_window": detail.get("in_window"),
        },
        "this_symbol_setups": _summarise_setups(fvg.setups(sym)),
        "this_symbol_mt_recent": _mt_events(fvg, sym),
        "pair_symbol": pair,
        "pair_setups": _summarise_setups(fvg.setups(pair)) if pair else None,
        "pair_mt_recent": _mt_events(fvg, pair) if pair else None,
        "chart_read": chart_read,
        "screenshot_age_s": round(shot_age, 1) if shot_age is not None else None,
        "htf_fvgs": _htf(fvg, sym, entry.get("entry")),
    }


def _htf(fvg: FVG, sym: str, price) -> dict | None:
    """4H / daily FVGs from the archived tape, with where the entry sits relative to each."""
    try:
        h = htf.htf_fvgs(fvg, sym)
    except Exception as e:   # optional context: never block the decision
        log.warning("htf fvgs: %s", e)
        return None
    if price:
        h = {**h, "4h": htf.relation(price, h["4h"]), "1d": htf.relation(price, h["1d"])}
    return h


def normalise(dec: dict) -> dict:
    d = (dec.get("decision") or "SKIP").upper()
    if d not in ("TAKE", "SKIP"):
        d = "SKIP"
    grade = dec.get("grade") or ("C" if d == "SKIP" else "B")
    size = (dec.get("size") or "").lower()
    if d == "SKIP":
        size = "none"
    elif grade == "B" or size not in ("full", "reduced"):
        size = "reduced" if grade == "B" or size != "full" else "full"
    try:
        conf = float(dec.get("confidence"))
    except (TypeError, ValueError):
        conf = None
    kind = dec.get("play_kind") or dec.get("play")
    play = kind if kind in prompts.PLAY_KINDS else "other"
    plan = dec.get("management_plan") if isinstance(dec.get("management_plan"), dict) else {}
    if dec.get("kill_conditions") and not plan.get("kill_conditions"):
        plan["kill_conditions"] = dec.get("kill_conditions")
    return {"decision": d, "grade": grade, "size": size, "confidence": conf, "play": play,
            "hard_rule": dec.get("hard_rule"), "reasons": dec.get("reasons") or [],
            "boosters": dec.get("boosters") or [], "plan": plan,
            "extra": {"unknowns": dec.get("unknowns"), "kill_conditions": plan.get("kill_conditions"),
                      "spotlight": dec.get("spotlight"), "sister_pair": dec.get("sister_pair"),
                      "targets": dec.get("targets")}}


def _keep_shots(entry_id, files, tag: str = ""):
    """Copy the screenshots a decision used (the rolling folder only keeps ~3 hours) so a
    reviewer can see the chart as it was: colours, lines, zones, gaps. tag="exit" = at settle."""
    if not files:
        return
    dst = config.DATA_DIR / "decision_shots"
    dst.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(files.split(",")):
        src = config.DATA_DIR / "shots" / f
        if src.exists():
            shutil.copyfile(src, dst / f"{entry_id}_{tag + '_' if tag else ''}{i}{src.suffix}")


def _latest_files():
    shots = store.latest_screenshot_set()
    return ",".join(s["file"] for s in shots) if shots else None


def review(fvg: FVG, entry: dict):
    detail = _detail(entry)
    row = _base_row(entry, detail)
    now = datetime.now(timezone.utc)
    age = (now - _iso_to_dt(entry["at"])).total_seconds()          # since fvg-mcp logged it
    bar_age = age
    if entry.get("entry_bar"):
        try:
            bar_age = now.timestamp() - int(entry["entry_bar"]) / 1000   # since the entry bar itself
        except (TypeError, ValueError):
            pass
    if age > config.MAX_ENTRY_AGE_S:
        row.update(decision="MISSED", size="none", reasons=[f"entry was {int(age)}s old when seen"])
        store.insert_decision(row)
        return row
    late_log = bar_age > config.MAX_ENTRY_AGE_S   # logged late: the live chart is from the wrong time
    if late_log:
        row["path"] = "late"

    row["rules_version"] = prompts.rules_version()
    signal = prompts.signal_of(entry, detail)
    row["play"] = prompts.play_name(entry.get("mt_tf"), signal, "continuation")   # kind refined by the model
    fired, news = rules_code.hard_rules(entry, detail, now)
    row["news"] = news or None
    if fired:
        hard = fired[0]   # the overarching reason first; the others are kept in reasons
        row.update(decision="SKIP", grade="C", size="none", hard_rule=hard, reasons=fired,
                   model_decision="code", path="code")
        try:   # keep the chart for code skips too: a reviewer must be able to see what was skipped
            files = _latest_files()
            row["screenshot"] = files
            _keep_shots(entry["id"], files)
        except OSError as e:
            log.warning("keep shots: %s", e)
        store.insert_decision(row)
        return row

    chart_read, shot_file, shot_age = None, None, None
    if late_log:
        row["vision_note"] = f"entry logged {int(bar_age / 60)} min after its bar: no chart read (screen is from the wrong time)"
    else:
        try:
            chart_read, shot_file, shot_age = chart_read_for_now()
        except Exception as e:  # must not block the decision
            log.warning("screenshot lookup failed: %s", e)
            row["error"] = f"vision: {e}"[:500]

    try:
        _keep_shots(entry["id"], shot_file if shot_age is not None and shot_age <= config.SCREENSHOT_MAX_AGE_S else None)
    except OSError as e:
        log.warning("keep shots: %s", e)
    if not late_log:
        row["vision_score"], row["vision_note"] = scanner.sanity_check(chart_read, entry)
    context = build_context(fvg, entry, detail, chart_read, shot_age)
    if late_log:
        context["note"] = row["vision_note"]
    if news:
        context["news"] = news
    # rule 2.8 from the archive (not the vision model): long inside an overhead 4H FVG / short below
    h = context.get("htf_fvgs") or {}
    if h.get("age_h") is not None and h["age_h"] <= 30 and entry.get("entry"):
        r28 = htf.rule_2_8(entry.get("direction"), float(entry["entry"]), h["4h"])
        if r28:
            row.update(decision="SKIP", grade="C", size="none", hard_rule=r28, reasons=[r28],
                       model_decision="code", path="code", chart_read=chart_read, screenshot=shot_file,
                       screenshot_age_s=shot_age, context=context)
            store.insert_decision(row)
            return row

    jv = jev.score(context)
    if jv:
        row["jev"] = jv
        row["jev_p_take"] = jv.get("p_take")
        if config.JEV_MODE == "gate" and jv.get("gate_rule"):
            row.update(decision="SKIP", grade="C", size="none", hard_rule=jv["gate_rule"],
                       confidence=jv.get("p_take"),
                       reasons=[f"Jev: {jv['gate_rule']}"],
                       play=prompts.play_name(entry.get("mt_tf"), signal, jv.get("play")), path="jev",
                       chart_read=chart_read, screenshot=shot_file, screenshot_age_s=shot_age,
                       context=context, model_decision=config.JEV_MODEL)
            store.insert_decision(row)
            return row

    try:
        context["course_passages"] = knowledge.passages_for(context)
    except Exception as e:  # search must never block a decision
        log.warning("knowledge search failed: %s", e)
    try:
        dec = normalise(llm.decide(prompts.decision_system(), prompts.decision_user(context)))
    except Exception as e:
        row.update(decision="ERROR", size="none", error=f"decide: {e}"[:500], context=context)
        store.insert_decision(row)
        return row

    context["_plan"] = dec["plan"]   # the management plan travels with the context snapshot
    context["_read"] = {k: dec["extra"].get(k) for k in ("spotlight", "sister_pair", "targets")}
    row.update(decision=dec["decision"], grade=dec["grade"], size=dec["size"],
               play=prompts.play_name(entry.get("mt_tf"), signal, dec["play"]),
               path="late" if late_log else "model",
               confidence=dec["confidence"], hard_rule=dec["hard_rule"], reasons=dec["reasons"],
               boosters=dec["boosters"], chart_read=chart_read, screenshot=shot_file,
               screenshot_age_s=shot_age, context=context, model_decision=config.DECISION_MODEL,
               model_vision=config.VISION_MODEL if chart_read else None)
    store.insert_decision(row)
    log.info("%s %s %s -> %s %s", entry["id"], entry["symbol"], entry.get("direction"),
             dec["decision"], dec["grade"])
    return row


# ---- outcomes + lessons ----------------------------------------------------------------------

def _kill_events(fvg: FVG, row) -> list:
    """Times (ms) after entry when a 5m Double Break printed AGAINST the trade: the instructor
    closes or rolls on that. Used to score the trade with his management rules."""
    try:
        evs = fvg.mt_events(row["symbol"], limit=400)   # ~2h of 1m+5m events can exceed 60
    except Exception:
        return []
    out = []
    start = _iso_to_dt(row["entry_at"]).timestamp() * 1000
    against = "lower" if row["direction"] == "bull" else "upper"
    for e in evs:
        txt = (e.get("text") or "").lower()
        if (e.get("tf") or "") != "5m" or "double break" not in txt or against not in txt:
            continue
        try:
            ms = _iso_to_dt(e["received_at"]).timestamp() * 1000
        except (KeyError, ValueError, TypeError):
            continue
        if ms > start:
            out.append(int(ms))
    return sorted(out)


def manage_pending(fvg: FVG, limit: int = 3) -> int:
    """Re-score settled TAKE/SKIP rows with the instructor's management rules on the price
    tape (close on a 5m DB against the play). Needs the archived day: retried a few times."""
    done = 0
    for row in store.managed_todo(limit):
        at = _iso_to_dt(row["entry_at"])
        kills = json.loads(row["kill_events"] or "[]")
        try:
            ticks = fvg.archived_prices(row["symbol"], at.strftime("%Y-%m-%d"))
            if at.hour >= 21:
                nxt = datetime.fromtimestamp(at.timestamp() + 86400, tz=timezone.utc).strftime("%Y-%m-%d")
                ticks = ticks + fvg.archived_prices(row["symbol"], nxt)
        except Exception as e:
            log.warning("archived_prices for %s: %s", row["entry_id"], e)
            store.managed_try(row["entry_id"])
            continue
        if not ticks or not row["entry"] or not row["stop"] or not row["target"]:
            store.managed_try(row["entry_id"])
            continue
        r, outcome = scanner.replay(ticks, row["direction"], row["entry"], row["stop"], row["target"],
                                    int(at.timestamp() * 1000), kills=kills)
        if r is None:
            store.managed_try(row["entry_id"])
            continue
        mult = store.SIZE_MULT.get(row["size"] or "none", 0.0) if row["decision"] == "TAKE" else 0.0
        store.update_decision(row["entry_id"], managed_r=r, managed_outcome=outcome,
                              managed_paper_r=round(r * mult, 3))
        done += 1
    return done


def settle(fvg: FVG, entry_row, scored: dict):
    r = scored.get("f_pnl_r")
    if r is None:
        return False
    try:
        store.update_decision(entry_row["entry_id"], kill_events=_kill_events(fvg, entry_row))
    except Exception as e:
        log.warning("kill events for %s: %s", entry_row["entry_id"], e)
    mult = store.SIZE_MULT.get(entry_row["size"] or "none", 0.0) if entry_row["decision"] == "TAKE" else 0.0
    store.update_decision(entry_row["entry_id"], r=float(r), outcome=scored.get("f_outcome"),
                          paper_r=round(float(r) * mult, 3),
                          closed_at=_ms_to_iso(scored.get("f_close_bar")))
    try:   # the chart at the time of the result, for exit / take-profit review
        _keep_shots(entry_row["entry_id"], _latest_files(), tag="exit")
    except OSError as e:
        log.warning("keep exit shots: %s", e)
    if entry_row["decision"] not in ("TAKE", "SKIP"):
        return True   # ERROR / MISSED rows are settled for the core book; nothing to learn from
    if not config.BUILTIN_LESSONS:
        return True   # Hermes reviews this trade (review_queue); no second DeepSeek pass
    outcome = {"r_if_taken_full": r, "outcome": scored.get("f_outcome"),
               "exit": scored.get("f_exit")}
    try:
        les = llm.decide(prompts.lesson_system(), prompts.lesson_user(entry_row, outcome),
                         purpose="lesson")
        store.update_decision(entry_row["entry_id"], lesson=les)
        store.add_lesson(entry_row["entry_id"], entry_row["symbol"], les.get("verdict"),
                         les.get("lesson"), les.get("rule_ref"), les.get("proposal"))
        learning.register_proposal(les, entry_row["entry_id"])
    except Exception as e:
        log.warning("lesson failed for %s: %s", entry_row["entry_id"], e)
        store.update_decision(entry_row["entry_id"], error=f"lesson: {e}"[:500])
    return True


# ---- main loop -------------------------------------------------------------------------------

def _wanted(entry: dict) -> bool:
    if entry.get("cascade") == "Gold Strategy" and not config.INCLUDE_GOLD:
        return False
    return True


def _safe_review(fvg: FVG, entry: dict):
    """review() must never take the loop down: anything unexpected becomes an ERROR row,
    which is retried while the entry is still fresh (see tick)."""
    try:
        return review(fvg, entry)
    except Exception as e:
        log.exception("review %s failed", entry.get("id"))
        detail = _detail(entry)
        try:
            row = _base_row(entry, detail)
        except Exception:
            row = {"entry_id": entry.get("id"), "symbol": entry.get("symbol"), "entry_at": entry.get("at"),
                   "reviewed_at": store.now_utc()}
        row.update(decision="ERROR", size="none", error=f"review: {type(e).__name__}: {e}"[:500])
        store.insert_decision(row)
        return row


def reevaluate_skips(fvg: FVG, limit: int = 3) -> int:
    """Rules changed? Code-skipped setups from the last 3 days are re-decided under the CURRENT
    rules (hard rules again; if none fires, Jev + the decision model, without a chart read since
    the screen is gone). The original decision is kept; the re-evaluation sits next to it."""
    if store.over_budget():
        return 0
    since = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 3 * 86400,
                                   tz=timezone.utc).isoformat()
    todo = store.reeval_todo(since, limit, prompts.rules_version())
    if not todo:
        return 0
    cache: dict[str, dict] = {}
    done = 0
    for row in todo:
        sym = row["symbol"]
        if sym not in cache:
            try:
                cache[sym] = {e["id"]: e for e in fvg.entries(sym, limit=150)}
            except Exception as e:
                log.warning("reeval entries %s: %s", sym, e)
                cache[sym] = {}
        entry = cache[sym].get(row["entry_id"])
        if not entry:
            store.update_decision(row["entry_id"], reeval={"note": "engine entry no longer available",
                                                           "rules_version": prompts.rules_version()})
            done += 1
            continue
        detail = _detail(entry)
        fired, news = rules_code.hard_rules(entry, detail, datetime.now(timezone.utc))
        at = store.now_utc()
        if fired:
            store.update_decision(row["entry_id"], reeval={"at": at, "still_skipped": fired[0],
                                                           "rules_version": prompts.rules_version()})
            done += 1
            continue
        context = build_context(fvg, entry, detail, None, None)
        context["note"] = "re-evaluation after a rule change: no chart read available for the time of the setup"
        try:
            context["course_passages"] = knowledge.passages_for(context)
        except Exception:
            pass
        jv = jev.score(context)
        rv = {"at": at, "rules_version": prompts.rules_version(), "jev_p_take": (jv or {}).get("p_take"),
              "jev_grade": (jv or {}).get("grade")}
        try:
            dec = normalise(llm.decide(prompts.decision_system(), prompts.decision_user(context), purpose="reeval"))
            rv.update(decision=dec["decision"], grade=dec["grade"], size=dec["size"], reasons=dec["reasons"][:6],
                      play=prompts.play_name(entry.get("mt_tf"), prompts.signal_of(entry, detail), dec["play"]))
        except Exception as e:   # transient (rate limit etc.): retried next tick, 3 tries per rules version
            log.warning("reeval %s: %s", row["entry_id"], e)
            try:
                old = json.loads(row["reeval"]) if row["reeval"] else {}
            except ValueError:
                old = {}
            same = old.get("rules_version") == rv["rules_version"]
            store.update_decision(row["entry_id"], reeval={"error": str(e)[:300], "rules_version": rv["rules_version"]},
                                  reeval_tries=((row["reeval_tries"] or 0) + 1) if same else 1)
            continue
        store.update_decision(row["entry_id"], reeval=rv)
        done += 1
    return done


def snapshot_setups(fvg: FVG):
    """What the engine is working on right now (armed / forming / ready), per symbol, with the
    code hard rule that would fire if it completed, plus the engine's feed health. Stored for
    the dashboard's pending-setups panel."""
    now = datetime.now(timezone.utc)
    out = {"at": now.isoformat(), "symbols": {}}
    for sym in config.SYMBOLS:
        try:
            s = fvg.setups(sym) or {}
        except Exception as e:
            out["symbols"][sym] = {"error": str(e)[:200]}
            continue
        rows = []
        for x in (s.get("setups") or [])[:12]:
            fake_entry = {"at": now.isoformat(), "symbol": sym, "mt_text": x.get("mt"), "cascade": x.get("cascade")}
            fake_detail = {"mt_cfg": x.get("mt_cfg"), "retrace": x.get("retrace"), "session": x.get("session"),
                           "in_window": x.get("in_window"), "trend_fallback": x.get("trend_fallback")}
            try:
                fired, _ = rules_code.hard_rules(fake_entry, fake_detail, now)
            except Exception:
                fired = []
            rows.append({k: x.get(k) for k in ("cascade", "direction", "mt", "mt_tf", "mt_cfg", "status", "stage",
                                               "armed", "ready", "retrace", "no_retrace", "two_m", "tf5_db",
                                               "conflict", "session", "in_window", "high_prob", "entry", "stop",
                                               "target", "sig_at", "forming", "chain")}
                        | {"would_skip": fired[0] if fired else None})
        out["symbols"][sym] = {"setups": rows, "health": s.get("health"), "conflict": s.get("conflict")}
    store.kv_set("setups_snapshot", out)
    return out


def _prefetch_htf(fvg: FVG):
    """Warm the HTF FVG cache outside review() so tape downloads never sit on a live decision."""
    for sym in config.SYMBOLS:
        try:
            htf.htf_fvgs(fvg, sym)
        except Exception as e:
            log.warning("htf prefetch %s: %s", sym, e)


def tick(fvg: FVG):
    learning.seed()
    changed = False
    by_id: dict[int, dict] = {}
    _prefetch_htf(fvg)
    try:
        snapshot_setups(fvg)
    except Exception as e:
        log.warning("setups snapshot: %s", e)
    for sym in config.SYMBOLS:
        rows = fvg.entries(sym, limit=40)
        for e in rows:
            by_id[e["id"]] = e
        baseline = store.kv_get(f"baseline:{sym}")
        if baseline is None:   # first run: don't review history, start from now
            store.kv_set(f"baseline:{sym}", max([e["id"] for e in rows], default=0))
            continue
        for e in sorted(rows, key=lambda x: x["id"]):
            if e["id"] <= baseline or not _wanted(e):
                continue
            if store.seen(e["id"]) and not store.retryable_error(e["id"], config.MAX_ENTRY_AGE_S):
                continue
            _safe_review(fvg, e)
            changed = True
    for row in store.open_decisions():
        scored = by_id.get(row["entry_id"])
        if scored and settle(fvg, row, scored):
            changed = True
    try:
        manage_pending(fvg)
    except Exception as e:
        log.warning("managed scoring failed: %s", e)
    try:   # the chart scanner: only inside its windows, only on a new screenshot set
        if config.SCAN_MINUTES > 0 and not store.over_budget():
            shots = store.latest_screenshot_set()
            files = ",".join(s["file"] for s in shots) if shots else None
            now = datetime.now(timezone.utc)
            if scanner.due(now, files):
                scanner.mark(now, files)   # before the read: a failed read must not retry every tick
                read, files, _ = chart_read_for_now()
                scanner.scan(fvg, read, files, now, force=True)
    except Exception as e:
        log.warning("scanner failed: %s", e)
    try:
        scanner.score_pending(fvg)
    except Exception as e:
        log.warning("scan scoring failed: %s", e)
    try:
        reevaluate_skips(fvg)
    except Exception as e:
        log.warning("re-evaluation failed: %s", e)
    try:   # per-symbol core book: mirror fvg-mcp's trade_history (no LLM calls)
        symbols.sync_if_due(fvg)
    except Exception as e:
        log.warning("core trades sync failed: %s", e)
    learning.promote_queued()
    try:
        learning.run_shadow()
    except Exception as e:   # the learning loop must never stop the review loop
        log.warning("shadow failed: %s", e)
    if changed:
        store.write_csv_file()
    return changed


def run_forever(stop: threading.Event):
    fvg = FVG()
    while not stop.is_set():
        try:
            tick(fvg)
            _state["last_error"] = None
        except Exception as e:
            log.exception("tick failed")
            _state["last_error"] = f"{type(e).__name__}: {e}"[:300]
        _state["last_loop"] = store.now_utc()
        _state["loops"] += 1
        stop.wait(config.POLL_SECONDS)


def status() -> dict:
    shot = store.latest_screenshot()
    cap = store.kv_get("capture_status") or {}
    # a status ping newer than the last screenshot explains why the screen is stale
    capture = cap.get("state") if cap and (not shot or cap.get("at", "") > shot["received_at"]) else None
    snap = store.kv_get("setups_snapshot") or {}
    stale = [f"{sym}: {v['health'].get('why')}" for sym, v in (snap.get("symbols") or {}).items()
             if isinstance(v.get("health"), dict) and v["health"].get("stale")]
    return {"paper_only": True, "capture_status": capture, "engine_feed_stale": stale or None,
            "capture_paused": bool(store.kv_get("capture_paused")), "symbols": config.SYMBOLS,
            "decision_model": config.DECISION_MODEL, "vision_model": config.VISION_MODEL,
            "jev_model": config.JEV_MODEL, "jev_mode": config.JEV_MODE,
            "rules_version": prompts.rules_version(),
            "key_set": bool(config.OPENROUTER_API_KEY),
            "last_loop_et": store.to_et(_state["last_loop"]), "loops": _state["loops"],
            "last_loop_ts": _iso_to_dt(_state["last_loop"]).timestamp() if _state["last_loop"] else None,
            "last_screenshot_ts": _iso_to_dt(shot["received_at"]).timestamp() if shot else None,
            "last_error": _state["last_error"],
            "spend_today_usd": round(store.spend_today(), 4), "daily_budget_usd": config.DAILY_BUDGET_USD,
            "over_budget": store.over_budget(),
            "last_screenshot_et": store.to_et(shot["received_at"]) if shot else None,
            "last_screenshot_kind": shot["kind"] if shot else None,
            "scanner": {"minutes": config.SCAN_MINUTES, "windows_et": config.SCAN_WINDOWS}}
