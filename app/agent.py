"""The review loop: new fvg-mcp entry -> chart read -> DeepSeek decision -> log -> outcome -> lesson.

PAPER ONLY. Nothing here places, modifies or cancels an order.
"""
import json
import logging
import shutil
import threading
import time
from datetime import datetime, timezone

from . import config, jev, knowledge, learning, llm, prompts, rules_code, store
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
    read = llm.read_chart([p.read_bytes() for p in paths], prompts.vision_prompt())
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
    }


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
    play = dec.get("play") if dec.get("play") in prompts.PLAYS else "other"
    return {"decision": d, "grade": grade, "size": size, "confidence": conf, "play": play,
            "hard_rule": dec.get("hard_rule"), "reasons": dec.get("reasons") or [],
            "boosters": dec.get("boosters") or [],
            "extra": {"unknowns": dec.get("unknowns"), "kill_conditions": dec.get("kill_conditions")}}


def _keep_shots(entry_id, files):
    """Copy the screenshots a decision used (the rolling folder only keeps ~3 hours)."""
    if not files:
        return
    dst = config.DATA_DIR / "decision_shots"
    dst.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(files.split(",")):
        src = config.DATA_DIR / "shots" / f
        if src.exists():
            shutil.copyfile(src, dst / f"{entry_id}_{i}{src.suffix}")


def review(fvg: FVG, entry: dict):
    detail = _detail(entry)
    row = _base_row(entry, detail)
    now = datetime.now(timezone.utc)
    age = (now - _iso_to_dt(entry["at"])).total_seconds()
    if age > config.MAX_ENTRY_AGE_S:
        row.update(decision="MISSED", size="none", reasons=[f"entry was {int(age)}s old when seen"])
        store.insert_decision(row)
        return row

    row["rules_version"] = prompts.rules_version()
    hard, news = rules_code.hard_rule(entry, detail, now)
    row["news"] = news or None
    if hard:
        row.update(decision="SKIP", grade="C", size="none", hard_rule=hard, reasons=[hard],
                   model_decision="code", path="code")
        store.insert_decision(row)
        return row

    chart_read, shot_file, shot_age = None, None, None
    try:
        chart_read, shot_file, shot_age = chart_read_for_now()
    except Exception as e:  # vision failure must not block the decision
        log.warning("vision failed: %s", e)
        row["error"] = f"vision: {e}"[:500]

    try:
        _keep_shots(entry["id"], shot_file if shot_age is not None and shot_age <= config.SCREENSHOT_MAX_AGE_S else None)
    except OSError as e:
        log.warning("keep shots: %s", e)
    context = build_context(fvg, entry, detail, chart_read, shot_age)
    if news:
        context["news"] = news

    jv = jev.score(context)
    if jv:
        row["jev"] = jv
        row["jev_p_take"] = jv.get("p_take")
        if config.JEV_MODE == "gate" and jv.get("gate_rule"):
            row.update(decision="SKIP", grade="C", size="none", hard_rule=jv["gate_rule"],
                       reasons=[f"Jev: {jv['gate_rule']}"], play=jv.get("play"), path="jev",
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

    row.update(decision=dec["decision"], grade=dec["grade"], size=dec["size"], play=dec["play"],
               path="model",
               confidence=dec["confidence"], hard_rule=dec["hard_rule"], reasons=dec["reasons"],
               boosters=dec["boosters"], chart_read=chart_read, screenshot=shot_file,
               screenshot_age_s=shot_age, context=context, model_decision=config.DECISION_MODEL,
               model_vision=config.VISION_MODEL if chart_read else None)
    store.insert_decision(row)
    log.info("%s %s %s -> %s %s", entry["id"], entry["symbol"], entry.get("direction"),
             dec["decision"], dec["grade"])
    return row


# ---- outcomes + lessons ----------------------------------------------------------------------

def settle(entry_row, scored: dict):
    r = scored.get("f_pnl_r")
    if r is None:
        return False
    mult = store.SIZE_MULT.get(entry_row["size"] or "none", 0.0) if entry_row["decision"] == "TAKE" else 0.0
    store.update_decision(entry_row["entry_id"], r=float(r), outcome=scored.get("f_outcome"),
                          paper_r=round(float(r) * mult, 3),
                          closed_at=_ms_to_iso(scored.get("f_close_bar")))
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


def tick(fvg: FVG):
    learning.seed()
    changed = False
    by_id: dict[int, dict] = {}
    for sym in config.SYMBOLS:
        rows = fvg.entries(sym, limit=40)
        for e in rows:
            by_id[e["id"]] = e
        baseline = store.kv_get(f"baseline:{sym}")
        if baseline is None:   # first run: don't review history, start from now
            store.kv_set(f"baseline:{sym}", max([e["id"] for e in rows], default=0))
            continue
        for e in sorted(rows, key=lambda x: x["id"]):
            if e["id"] <= baseline or store.seen(e["id"]) or not _wanted(e):
                continue
            review(fvg, e)
            changed = True
    for row in store.open_decisions():
        scored = by_id.get(row["entry_id"])
        if scored and settle(row, scored):
            changed = True
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
    return {"paper_only": True, "symbols": config.SYMBOLS,
            "decision_model": config.DECISION_MODEL, "vision_model": config.VISION_MODEL,
            "jev_model": config.JEV_MODEL, "jev_mode": config.JEV_MODE,
            "key_set": bool(config.OPENROUTER_API_KEY),
            "last_loop_et": store.to_et(_state["last_loop"]), "loops": _state["loops"],
            "last_error": _state["last_error"],
            "last_screenshot_et": store.to_et(shot["received_at"]) if shot else None}
