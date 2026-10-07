"""Jev (TypeSafe "System One") playbook: one fast call (~100 ms) that scores a setup against
EVERY rule we know, as probabilities. The playbook is generated from rules/ (rulebook §2 hard
rules, §3 must-haves, boosters and downgrades, the amendments), so an approved amendment
changes Jev's questions on the next call. Jev is not trained; its "training" is this playbook.

Used on: engine setups (shadow next to DeepSeek, or gate), the scanner's forming setups, and
skipped trades re-evaluated under corrected rules.

JEV_MODE=shadow (default): recorded, decides nothing. gate: a hard rule Jev puts at
>= JEV_GATE_P skips the setup without calling DeepSeek.
"""
import logging
import re

from . import config, llm, prompts

log = logging.getLogger("jev")

_cache = {"version": None, "questions": None, "playbook": None}

# judgment hard rules whose evidence is mostly in the chart read / pair data; the mechanical
# ones (2DB, ND, news, window, retrace) are decided in code before Jev is called
CODE_RULES = ("1", "2", "3", "4", "6", "13")


def _section(text: str, start: str, end: str | None) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j] if j > 0 else text[i:]


def _bullets(block: str) -> list:
    out, cur = [], None
    for line in block.splitlines():
        if line.startswith("- "):
            if cur:
                out.append(cur.strip())
            cur = line[2:]
        elif cur is not None and line.startswith("  "):
            cur += " " + line.strip()
        elif cur is not None:
            out.append(cur.strip())
            cur = None
    if cur:
        out.append(cur.strip())
    return out


def _numbered(block: str) -> list:
    """[(number, text)] for '1. ...' items with their continuation lines."""
    out, cur = [], None
    for line in block.splitlines():
        m = re.match(r"^(\d+)\.\s+(.*)", line)
        if m:
            if cur:
                out.append(cur)
            cur = [m.group(1), m.group(2)]
        elif cur and line.startswith("   "):
            cur[1] += " " + line.strip()
        elif cur:
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return [(n, t.strip()) for n, t in out]


def _sentences(text: str) -> list:
    text = text.split(":", 1)[1] if ":" in text[:60] else text
    return [s.strip().rstrip(".") for s in re.split(r";|\.\s+(?=[A-Z])", text.replace("\n", " ")) if len(s.strip()) > 12]


def build_playbook() -> dict:
    """Questions keyed by id, plus a readable list for the dashboard."""
    rb = prompts._read("rulebook.md")
    am = prompts._read("amendments.md")
    q, readable = {}, []
    hard = _section(rb, "## 2. Hard rules", "## 3.")
    for n, text in _numbered(hard):
        if n in CODE_RULES:
            continue
        q[f"hard_{n}"] = {"type": "noul", "instructions": (
            f"Hard rule §2.{n} clearly applies to this setup, based only on the evidence in the "
            f"state (if the evidence is missing, answer no): {text}")}
        readable.append(("hard rule", f"§2.{n}", text))
    grading = _section(rb, "## 3. Grading", "## 4.")
    must = _section(grading, "Must-haves:", "Boosters")
    for i, s in enumerate(_sentences(must)[:8], 1):
        q[f"must_{i}"] = {"type": "noul", "instructions": f"This must-have is satisfied by the evidence in the state: {s}"}
        readable.append(("must-have", f"M{i}", s))
    boosters = _section(grading, "Boosters (count them):", "Live-session plays")
    for i, b in enumerate(_bullets(boosters)[:10], 1):
        q[f"boost_{i}"] = {"type": "noul", "instructions": f"This booster is present: {b}"}
        readable.append(("booster", f"B{i}", b))
    downgrades = _section(grading, "Downgrades (reduce size):", "##")
    for i, d in enumerate(_sentences(downgrades)[:10], 1):
        q[f"down_{i}"] = {"type": "noul", "instructions": f"This downgrade applies (reduce size): {d}"}
        readable.append(("downgrade", f"D{i}", d))
    if am.strip():
        q["amend_ok"] = {"type": "noul", "instructions": (
            "The setup complies with every approved amendment below (answer no if any amendment "
            "forbids it):\n" + am[-3000:])}
        readable.append(("amendments", "A", "complies with every approved amendment"))
    q["play"] = {"type": "choice", "instructions": "Which kind of play is this setup?",
                 "criteria": dict(prompts.PLAY_KINDS)}
    q["grade"] = {"type": "choice", "instructions": "Grade per rulebook §3.", "criteria": {
        "A+": "all must-haves and 3+ boosters", "A": "all must-haves and 1-2 boosters",
        "B": "must-haves met but a downgrade applies", "C": "a must-have is missing"}}
    q["take"] = {"type": "choice", "instructions": (
        "Would a disciplined Fractal Effects trader take this setup? TAKE needs every must-have "
        "met and no hard rule; missing evidence for a must-have means SKIP."),
        "criteria": {"TAKE": "all must-haves are met and no hard rule applies",
                     "SKIP": "a must-have is missing or a hard rule applies"}}
    return {"questions": q, "readable": readable}


def playbook() -> dict:
    v = prompts.rules_version()
    if _cache["version"] != v:
        pb = build_playbook()
        _cache.update(version=v, questions=pb["questions"], playbook=pb["readable"])
    return {"version": v, "questions": _cache["questions"], "readable": _cache["playbook"]}


def questions() -> dict:
    return playbook()["questions"]


def _state(context: dict) -> dict:
    keep = ("now", "engine", "this_symbol_setups", "this_symbol_mt_recent", "pair_symbol",
            "pair_setups", "pair_mt_recent", "chart_read", "news", "htf_fvgs", "spotted")
    return {k: context.get(k) for k in keep if context.get(k) is not None}


def score(context: dict) -> dict | None:
    if config.JEV_MODE == "off":
        return None
    try:
        qs = questions()
        res = llm.system_one(_state(context), qs)
    except Exception as e:
        log.warning("jev failed: %s", e)
        return {"error": str(e)[:300]}
    a = res["answers"]
    take = a.get("take") or {}

    def nouls(prefix):
        return {k: (a.get(k) or {}).get("noul") for k in qs if k.startswith(prefix)}
    out = {
        "model": res.get("model"), "ms": res.get("ms"), "playbook_version": playbook()["version"],
        "p_take": (take.get("probabilities") or {}).get("TAKE"),
        "grade": (a.get("grade") or {}).get("choice"),
        "grade_probs": (a.get("grade") or {}).get("probabilities"),
        "play": (a.get("play") or {}).get("choice"),
        "rules": nouls("hard_"), "must_haves": nouls("must_"), "boosters": nouls("boost_"),
        "downgrades": nouls("down_"), "amendments_ok": (a.get("amend_ok") or {}).get("noul"),
    }
    out["boosters_present"] = sum(1 for p in out["boosters"].values() if p is not None and p >= 0.5)
    out["must_haves_missing"] = [k for k, p in out["must_haves"].items() if p is not None and p < 0.5]
    sure = [(k, p) for k, p in out["rules"].items() if p is not None and p >= config.JEV_GATE_P]
    if sure:
        k = max(sure, key=lambda x: x[1])[0]
        out["gate_rule"] = f"§2.{k.split('_')[1]} (Jev {out['rules'][k]:.0%})"
    else:
        out["gate_rule"] = None
    return out
