"""Prompt text. The rulebook files are re-read on every call, so editing rules/ (or approving
an amendment) takes effect without a restart."""
import json

from . import config, store


def _read(name: str) -> str:
    p = config.RULES_DIR / name
    return p.read_text() if p.exists() else ""


VISION_PROMPT = """You are reading a TradingView screenshot for a futures trader who uses the
Fractal Effects "Market Translator" and "Spotlight" indicators.

Layout: {layout}

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
  "readability": "good" | "partial" | "poor"
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
        live_rules=_read("live_rules.md"), lessons=_lessons_block())


def decision_user(context: dict) -> str:
    return ("Setup to review (all times ET). The 'engine' block is fvg-mcp's own data; "
            "'chart_read' is a vision model's reading of the latest screenshot (may be null or "
            "partial).\n\n" + json.dumps(context, indent=1, default=str))


LESSON_SYSTEM = """You review a finished PAPER trade for a Fractal Effects trader and write a
short, specific lesson that would make the next decision better. Use the rulebook language.
Do not overfit: one trade is weak evidence. Only propose a rule change if this trade clearly
exposes a gap or a contradiction in the rules, and phrase it as a proposal for the trader to
approve.

Rulebook (for reference):
{rulebook}

Reply with ONE JSON object:
{{
  "verdict": "right_take" | "wrong_take" | "right_skip" | "wrong_skip",
  "lesson": "one or two sentences, concrete (what to look for next time)",
  "rule_ref": "rule section this concerns, e.g. §2.6",
  "proposal": "a proposed rule change, or null"
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
        "reasons": j(row["reasons"]), "hard_rule": row["hard_rule"],
        "chart_read_at_entry": j(row["chart_read"]),
        "result": outcome,
    }
    return json.dumps(payload, indent=1, default=str)
