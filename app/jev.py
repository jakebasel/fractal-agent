"""Jev (TypeSafe "System One") pass: one fast call that scores every judgment hard rule, the
grade, the play and P(TAKE) as probabilities.

JEV_MODE=shadow (default): recorded next to DeepSeek's decision so we can measure agreement and
calibration against settled results before trusting it. JEV_MODE=gate: a hard rule Jev puts at
>= JEV_GATE_P skips the setup without calling DeepSeek (faster, cheaper).
"""
import logging

from . import config, llm, prompts

log = logging.getLogger("jev")

# judgment hard rules (rulebook §2) - the mechanical ones are checked in rules_code.py
HARD_RULES = {
    "r2_4": "§2.4 The index has a false day, or an unresolved 2DB (two Double Breaks in opposite "
            "directions with no reversal-zone resolution).",
    "r2_5": "§2.5 This is a DB setup and a 5m candle BODY has closed beyond that DB's white "
            "reversal line (the DB is failing).",
    "r2_7": "§2.7 A 1:3 target does not fit before an obstacle (purple/blue zone, DSD, prior "
            "high/low, 4H FVG) in the trade direction.",
    "r2_8": "§2.8 The trade enters long deeper into an overhead 4H FVG, or short deeper into one below.",
    "r2_9": "§2.9 Majority rules is violated: 2 of 3 indices show a 5m DB in the other direction.",
    "r2_10": "§2.10 It buys the weaker index or sells the stronger one while the pair index offers "
             "the same idea.",
    "r2_11": "§2.11 More than 5-7 candles of consolidation at the zone, or wick-to-wick candles "
             "with no foothold.",
    "r2_12": "§2.12 The higher-timeframe target is already delivered and the setup is not complete "
             "on both indices.",
}


def questions() -> dict:
    q = {k: {"type": "noul", "instructions": f"Based only on the evidence in the state, this "
                                             f"hard rule clearly applies: {v}"}
         for k, v in HARD_RULES.items()}
    q["take"] = {"type": "choice", "instructions": (
        "Would a disciplined Fractal Effects trader take this setup? TAKE needs: a clear Market "
        "Translator signal on the setup timeframe, a real retracement into a defined zone, the "
        "first FVG at each step, and room for 1:3. Missing evidence for a must-have means SKIP."),
        "criteria": {"TAKE": "all must-haves are met and no hard rule applies",
                     "SKIP": "a must-have is missing or a hard rule applies"}}
    q["grade"] = {"type": "choice", "instructions": "Grade per rulebook §3.", "criteria": {
        "A+": "all must-haves and 3+ boosters", "A": "all must-haves and 1-2 boosters",
        "B": "must-haves met but a downgrade applies", "C": "a must-have is missing"}}
    q["play"] = {"type": "choice", "instructions": "Which play is this setup?",
                 "criteria": dict(prompts.PLAYS)}
    return q


def _state(context: dict) -> dict:
    keep = ("now", "engine", "this_symbol_setups", "this_symbol_mt_recent", "pair_symbol",
            "pair_setups", "pair_mt_recent", "chart_read", "news")
    return {k: context.get(k) for k in keep if context.get(k) is not None}


def score(context: dict) -> dict | None:
    if config.JEV_MODE == "off":
        return None
    try:
        res = llm.system_one(_state(context), questions())
    except Exception as e:
        log.warning("jev failed: %s", e)
        return {"error": str(e)[:300]}
    a = res["answers"]
    take = a.get("take") or {}
    out = {
        "model": res.get("model"), "ms": res.get("ms"),
        "p_take": (take.get("probabilities") or {}).get("TAKE"),
        "grade": (a.get("grade") or {}).get("choice"),
        "grade_probs": (a.get("grade") or {}).get("probabilities"),
        "play": (a.get("play") or {}).get("choice"),
        "rules": {k: (a.get(k) or {}).get("noul") for k in HARD_RULES},
    }
    sure = [(k, p) for k, p in out["rules"].items() if p is not None and p >= config.JEV_GATE_P]
    out["gate_rule"] = HARD_RULES[max(sure, key=lambda x: x[1])[0]] if sure else None
    return out
