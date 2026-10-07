"""Prompt text. The rulebook files are re-read on every call, so editing rules/ (or approving
an amendment) takes effect without a restart."""
import hashlib
import json

from . import config, store

RULE_FILES = ("amendments.md", "rulebook.md", "live_rules.md")

# the plays the strategy names (rulebook + live sessions + Reversal Set Up video)
PLAYS = {
    "DB continuation": "Double Break, retracement into the DB leg / zone, cascade in the DB direction",
    "M continuation": "single M signal, retracement and cascade in the M direction",
    "2M return": "two Ms; price returns to the first 5m FVG between them",
    "true triangle": "M, M, DB: return to the FVG between the Ms, then the DB direction",
    "false triangle": "M, DB, M: stick with the DB",
    "2DB": "two Double Breaks; resolved by the reversal-zone rule",
    "reversal set up": "HTF FVG / liquidity hit + body close through a white line + reversal zone",
    "M via reversal zone": "reversal zone after a close through the M line used to continue the M",
    "1m play": "1m signal skipping the 5m step: immediate rebalance, 1m FVG, 30s FVG, close",
    "blue/purple zone play": "pullback into the NY blue zone or Asia purple zone, then the cascade",
    "other": "none of the above",
}


def _read(name: str) -> str:
    p = config.RULES_DIR / name
    return p.read_text() if p.exists() else ""


def rules_version() -> str:
    """Short hash of the rule files: every decision records which rulebook it was made under."""
    h = hashlib.sha1()
    for f in RULE_FILES:
        h.update(_read(f).encode())
    v = h.hexdigest()[:8]
    store.note_rule_version(v, _read("amendments.md"))
    return v


VISION_PROMPT = """You are reading a TradingView screenshot for a futures trader who uses the
Fractal Effects "Market Translator" and "Spotlight" indicators.

Layout: {layout}

You may get one image per TradingView window, left window first.
If an image is NOT a TradingView chart (a video, browser page, desktop...), set "readability"
to "not_chart" and return no charts for it.

Report ONLY what is visible. If something is not visible or unreadable, use null / "unknown".
Do not guess prices you cannot read from the axis.

Return one JSON object:
{{
  "charts": [   // one per visible chart panel
    {{
      "symbol": "MNQ" | "MES" | "MYM" | "other",
      "timeframe": "5m" | "1m" | "unknown",
      "last_price": number | null,
      "signals": [ {{"label": "M"|"2M"|"DB"|"2DB", "side": "above_price"|"below_price",
                     "approx_price": number|null, "recent": true|false}} ],
      "white_lines": [ {{"label": "M"|"2M"|"DB"|"2DB", "price": number|null,
                         "body_closed_through": true|false|null}} ],
      "reversal_zones": [ {{"color": "green"|"red", "top": number|null, "bottom": number|null,
                            "price_inside_or_tapped": true|false|null}} ],
      "zones": [ {{"type": "purple"|"maroon"|"blue"|"dark_blue"|"ndog"|"nwog"|"opening_fvg"|"dsd_high"|"dsd_low",
                   "top": number|null, "bottom": number|null, "relation": "above"|"below"|"price_inside"}} ],
      "spotlight": {{"dr_box": "red"|"green"|"none"|"unknown", "confirmation": "bull"|"bear"|"none"|"unknown",
                     "both_sides_broken": true|false|null}},
      "ema": {{"price_vs_20": "above"|"below"|"unknown", "price_vs_238": "above"|"below"|"unknown"}},
      "trend_table": {{"5m": "up"|"down"|null, "1h": "up"|"down"|null, "4h": "up"|"down"|null, "d": "up"|"down"|null}},
      "structure": "trending_up"|"trending_down"|"consolidating"|"unknown",
      "consolidation_candles": number | null,
      "notes": "anything else that matters, one or two sentences"
    }}
  ],
  "screen_time_et": "the clock shown on screen if visible, else null",
  "readability": "good" | "partial" | "poor" | "not_chart"
}}"""


def vision_prompt() -> str:
    return VISION_PROMPT.format(layout=config.SCREEN_LAYOUT)


DECISION_SYSTEM = """You are the AI review layer of a PAPER-trading system for the Fractal
Effects futures strategy. A deterministic rules engine already found the setup below; you decide
whether the instructor would actually take it, using ONLY the rulebook. Be strict: the default
when evidence is missing for a must-have is SKIP or reduced size, never invention.

=== RULEBOOK (priority order: amendments > rulebook > live rules) ===
--- amendments.md ---
{amendments}
--- rulebook.md ---
{rulebook}
--- live_rules.md ---
{live_rules}

=== LESSONS FROM PAST PAPER TRADES (most recent first; treat as evidence, not law) ===
{lessons}

Reply with ONE JSON object and nothing else:
{{
  "decision": "TAKE" | "SKIP",
  "play": one of {plays},
  "grade": "A+" | "A" | "B" | "C",
  "size": "full" | "reduced" | "none",
  "confidence": 0.0-1.0,
  "hard_rule": "the hard rule number + short name that forced a SKIP, or null",
  "boosters": ["each booster that is present"],
  "reasons": ["3-6 short reasons, each citing a rule section, e.g. '§2.6 retracement too shallow'"],
  "unknowns": ["things you could not verify that matter"],
  "kill_conditions": ["what would invalidate the trade after entry"]
}}
SKIP must have size "none". TAKE with grade B must have size "reduced"."""


def _lessons_block() -> str:
    rows = store.recent_lessons(config.LESSONS_IN_PROMPT)
    if not rows:
        return "(none yet)"
    out = []
    for r in rows:
        line = f"- [{r['verdict']}] {r['symbol']}: {r['lesson']}"
        if r["rule_ref"]:
            line += f" ({r['rule_ref']})"
        out.append(line)
    return "\n".join(out)


def decision_system() -> str:
    return DECISION_SYSTEM.format(
        amendments=_read("amendments.md"), rulebook=_read("rulebook.md"),
        live_rules=_read("live_rules.md"), lessons=_lessons_block(),
        plays=json.dumps(list(PLAYS)))


def decision_user(context: dict) -> str:
    return ("Setup to review (all times ET). The 'engine' block is fvg-mcp's own data; "
            "'chart_read' is a vision model's reading of the latest screenshot (may be null or "
            "partial); 'course_passages' are the most relevant excerpts from the instructor's "
            "own course transcripts and lessons (quote them when they decide the call; the "
            "rulebook still wins on conflicts unless the passage is from the Reversal Set Up "
            "video).\n\n" + json.dumps(context, indent=1, default=str))


LESSON_SYSTEM = """You review a finished PAPER trade for a Fractal Effects trader and write a
short, specific lesson that would make the next decision better. Use the rulebook language.
Do not overfit: one trade is weak evidence. Only propose a rule change if this trade clearly
exposes a gap or a contradiction in the rules. Phrase a proposal as ONE testable rule another
reviewer could apply to any setup, in the form "IF <condition visible in the data> THEN
<TAKE | SKIP | reduce size>". Proposals are shadow-tested on past and future trades and only the
trader can approve them.

Rulebook (for reference):
{rulebook}

Reply with ONE JSON object:
{{
  "verdict": "right_take" | "wrong_take" | "right_skip" | "wrong_skip",
  "lesson": "one or two sentences, concrete (what to look for next time)",
  "rule_ref": "rule section this concerns, e.g. §2.6",
  "proposal": "IF ... THEN ... (a testable rule change), or null",
  "proposal_title": "3-6 word name for the proposal, or null"
}}
A TAKE that lost is wrong_take only if the rules or chart gave a reason to skip; a rule-following
loss is a 'business expense' and still right_take. Same logic for skips."""


def lesson_system() -> str:
    return LESSON_SYSTEM.format(rulebook=_read("rulebook.md"))


def lesson_user(row, outcome: dict) -> str:
    def j(x):
        try:
            return json.loads(x) if x else None
        except ValueError:
            return x
    payload = {
        "symbol": row["symbol"], "direction": row["direction"], "signal": row["mt_text"],
        "signal_tf": row["mt_tf"], "config": row["mt_cfg"], "retrace": row["retrace"],
        "entry": row["entry"], "stop": row["stop"], "target": row["target"],
        "decision": row["decision"], "grade": row["grade"], "size": row["size"],
        "play": row["play"], "reasons": j(row["reasons"]), "hard_rule": row["hard_rule"],
        "chart_read_at_entry": j(row["chart_read"]),
        "result": outcome,
    }
    return json.dumps(payload, indent=1, default=str)


SCAN_SYSTEM = """You scan a live chart read for the Fractal Effects strategy and report any
rulebook play that is FORMING or READY which the rules engine has not armed. The engine only
finds M/DB-armed FVG cascades; you look for what it misses: the Reversal Set Up (§5: HTF level
hit + body close through a white line + reversal zone printed), 1m plays, blue/purple zone
plays, 2M returns, triangles. Be conservative: report only what the chart read supports, and
say "forming" unless the trigger is in. Never report a setup the engine already has armed in
the same direction (check `engine_armed`).

Rulebook §5 and plays:
{reversal}

Reply with ONE JSON object: {{"setups": [{{"symbol": "MNQ1!"|"MES1!", "play": one of {plays},
"direction": "bull"|"bear", "stage": "forming"|"ready"|"entered", "entry": number|null,
"stop": number|null, "target": number|null, "confidence": 0.0-1.0,
"reasons": ["2-4 short reasons citing what was read"], "engine_has_it": true|false}}]}}
Empty list if nothing qualifies."""


def scan_system() -> str:
    rb = _read("rulebook.md")
    i = rb.find("## 5.")
    return SCAN_SYSTEM.format(reversal=rb[i:] if i >= 0 else rb[-3000:], plays=json.dumps(list(PLAYS)))


def scan_user(chart_read, armed, now) -> str:
    return json.dumps({"now_et": now.astimezone(config.ET).strftime("%a %Y-%m-%d %H:%M ET"),
                       "engine_armed": armed, "chart_read": chart_read}, indent=1, default=str)


MATCH_SYSTEM = """You file proposed rule changes for a trading strategy. Given a NEW proposal
and the list of EXISTING hypotheses, decide whether the new one says the same thing as an
existing one (same condition, same action; wording may differ).
Reply with ONE JSON object: {"same_as": <existing id or null>, "title": "3-6 word name"}"""


def match_user(proposal: str, existing) -> str:
    return json.dumps({"new_proposal": proposal,
                       "existing": [{"id": h["id"], "rule": h["rule"]} for h in existing]}, indent=1)


SHADOW_SYSTEM = """You are re-deciding a PAPER trade setup for the Fractal Effects strategy to
test proposed rule changes. For EACH hypothesis, imagine ONLY that one change is added to the
rulebook (highest priority) and say what the decision would be. If the hypothesis does not
apply to this setup, the decision stays the same as the actual one. Judge only from the data
given; you do not know the outcome.

=== RULEBOOK ===
{rulebook}

Reply with ONE JSON object:
{{"<hypothesis id>": {{"decision": "TAKE"|"SKIP", "size": "full"|"reduced"|"none",
                        "applies": true|false, "why": "one short sentence"}}, ...}}"""


def shadow_system() -> str:
    return SHADOW_SYSTEM.format(rulebook=_read("amendments.md") + "\n" + _read("rulebook.md"))


def shadow_user(row, hyps) -> str:
    def j(x):
        try:
            return json.loads(x) if x else None
        except ValueError:
            return x
    setup = j(row["context"]) or {
        "engine": {"symbol": row["symbol"], "direction": row["direction"], "cascade": row["cascade"],
                   "signal": row["mt_text"], "signal_tf": row["mt_tf"], "config": row["mt_cfg"],
                   "retrace": row["retrace"], "session": row["session"],
                   "entry_at": store.to_et(row["entry_at"])}}
    if isinstance(setup, dict):
        setup.pop("course_passages", None)
    return json.dumps({
        "setup": setup,
        "actual": {"decision": row["decision"], "grade": row["grade"], "size": row["size"],
                   "hard_rule": row["hard_rule"], "reasons": j(row["reasons"]),
                   "play": row["play"]},
        "hypotheses": [{"id": h["id"], "rule": h["rule"]} for h in hyps],
    }, indent=1, default=str)
