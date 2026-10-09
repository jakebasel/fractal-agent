"""All settings come from environment variables (set them in Coolify)."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _env(name, default=""):
    return os.environ.get(name, default).strip()


# --- where things live ------------------------------------------------------------------
DATA_DIR = Path(_env("DATA_DIR", "/data"))
RULES_DIR = Path(_env("RULES_DIR", str(Path(__file__).resolve().parent.parent / "rules")))

# --- the rules engine (fvg-mcp), read-only ---------------------------------------------
FVG_MCP_URL = _env("FVG_MCP_URL", "https://fvg.motivationpro.tech/mcp")
SYMBOLS = [s.strip() for s in _env("SYMBOLS", "MNQ1!,MES1!").split(",") if s.strip()]
# the index each symbol is compared with for divergence (stronger/weaker pair)
PAIR = {"MNQ1!": "MES1!", "MES1!": "MNQ1!", "NQ1!": "ES1!", "ES1!": "NQ1!"}
POLL_SECONDS = int(_env("POLL_SECONDS", "15"))
# only review entries this fresh; older ones (e.g. after a restart) are logged as missed
MAX_ENTRY_AGE_S = int(_env("MAX_ENTRY_AGE_S", "300"))
# include the "Gold Strategy" rows fvg-mcp also records? default no: Fractal Effects only
INCLUDE_GOLD = _env("INCLUDE_GOLD", "0") == "1"

import json as _json
# --- AI (Anthropic direct, or OpenRouter) --------------------------------------------------
# Jake 2026-10-08: OpenRouter ran out of credits and every decision errored for a day, so
# the agent talks to the Claude API directly when ANTHROPIC_API_KEY is set. Any model id
# starting with "claude-" goes to Anthropic; everything else still goes through OpenRouter
# (Jev's /systemone endpoint only exists there).
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
ANTHROPIC_URL = _env("ANTHROPIC_URL", "https://api.anthropic.com/v1/messages")
ANTHROPIC_VERSION = _env("ANTHROPIC_VERSION", "2023-06-01")
# $ per million tokens, for the spend log and the daily budget (Haiku-class defaults;
# override to match the current price list)
ANTHROPIC_PRICE_IN_PER_M = float(_env("ANTHROPIC_PRICE_IN_PER_M", "1.0"))
ANTHROPIC_PRICE_OUT_PER_M = float(_env("ANTHROPIC_PRICE_OUT_PER_M", "5.0"))
CLAUDE_CHEAP_MODEL = _env("CLAUDE_CHEAP_MODEL", "claude-haiku-5-5")   # the lowest-price Claude
# Jake 2026-10-08: Haiku for the per-setup work, Fable for the bigger, rarer calls. HEAVY_PURPOSES
# names which call purposes go to HEAVY_MODEL (lesson = after a settled trade, hypothesis =
# proposal matching, reeval = re-judging an old skip under new rules); everything else (decision,
# vision, scan, shadow) stays on the cheap model. HEAVY_MAX_PER_DAY caps the heavy calls per ET
# day; past the cap they fall back to the cheap model.
HEAVY_MODEL = _env("HEAVY_MODEL", "claude-fable-5-1")
# reeval is NOT heavy by default: the first three Fable re-evaluations cost ~$0.65 each (the
# prompt carries the whole setup context) and blew the daily budget in one tick.
HEAVY_PURPOSES = {x.strip() for x in _env("HEAVY_PURPOSES", "lesson,hypothesis").split(",") if x.strip()}
HEAVY_MAX_PER_DAY = int(_env("HEAVY_MAX_PER_DAY", "10"))
# $ per million tokens by model-id prefix, for the spend log and the daily budget. Set these to
# the current price list; unknown models use ANTHROPIC_PRICE_*_PER_M.
ANTHROPIC_PRICES = _json.loads(_env("ANTHROPIC_PRICES", '{"claude-haiku": [1.0, 5.0], "claude-sonnet": [3.0, 15.0], "claude-opus": [15.0, 75.0], "claude-fable": [15.0, 75.0]}') or "{}")
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
OPENROUTER_URL = _env("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
# DeepSeek V3.2 (Jake 2026-10-07: newer and cheaper than deepseek-chat). V4 Pro is a thinking
# model that spent its whole budget reasoning and answered nothing; it stays as a fallback
# with reasoning disabled. take/skip + lessons + shadow + scans.
DECISION_MODEL = _env("DECISION_MODEL", CLAUDE_CHEAP_MODEL if ANTHROPIC_API_KEY else "deepseek/deepseek-v3.2")
DECISION_MAX_TOKENS = int(_env("DECISION_MAX_TOKENS", "4000"))
# reasoning control for thinking models (OpenRouter 'reasoning' object), e.g. {"effort":"low"}
# or {"enabled": false}; empty = send nothing
DECISION_REASONING = _json.loads(_env("DECISION_REASONING", '{"enabled": false}') or "null")
# OpenRouter falls back to these, in order, when the decision model is rate-limited or down
DECISION_FALLBACK_MODELS = [m.strip() for m in _env("DECISION_FALLBACK_MODELS",
                                                    "deepseek/deepseek-v4-pro,deepseek/deepseek-chat").split(",") if m.strip()]
VISION_MODEL = _env("VISION_MODEL", CLAUDE_CHEAP_MODEL if ANTHROPIC_API_KEY else "google/gemini-2.5-flash")   # reads the screenshot
LLM_TIMEOUT_S = int(_env("LLM_TIMEOUT_S", "60"))
# Jev (TypeSafe "System One" model) via OpenRouter's /systemone endpoint: fast rule-by-rule
# probabilities. JEV_MODE: off | shadow (score every setup, decide nothing; default) |
# gate (a hard rule Jev is sure about skips without calling DeepSeek).
JEV_MODEL = _env("JEV_MODEL", "typesafe/jev-1.13")
JEV_URL = _env("JEV_URL", "https://openrouter.ai/api/v1/systemone")
JEV_MODE = _env("JEV_MODE", "shadow").lower()
JEV_GATE_P = float(_env("JEV_GATE_P", "0.9"))
JEV_TIMEOUT_S = int(_env("JEV_TIMEOUT_S", "15"))

# --- screenshots from the Mac -----------------------------------------------------------------
AGENT_TOKEN = _env("AGENT_TOKEN")             # shared secret for /screenshot and /log.csv
SCREENSHOT_MAX_AGE_S = int(_env("SCREENSHOT_MAX_AGE_S", "180"))
SCREEN_LAYOUT = _env(
    "SCREEN_LAYOUT",
    "Two TradingView windows side by side: 5-minute charts on the LEFT, 1-minute charts on "
    "the RIGHT. Each window shows MNQ (Nasdaq micro) and MES (S&P micro), possibly MYM (Dow).",
)

# --- news filter (rule 2.2): high-impact USD events from the public weekly calendar ---------
NEWS_FILTER = _env("NEWS_FILTER", "1") == "1"
NEWS_URL = _env("NEWS_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json")
# red-folder (high-impact) USD releases only; skip from the release until NEWS_AFTER_MIN after it
# (Jake 2026-10-07: the bracket is AFTER the event only, about 2 hours; before it trades normally)
NEWS_BEFORE_MIN = int(_env("NEWS_BEFORE_MIN", "0"))
NEWS_AFTER_MIN = int(_env("NEWS_AFTER_MIN", "120"))

# --- spend guard: optional work (shadow tests, scanner, Jev backfill) pauses when today's
# OpenRouter spend passes this; live decisions always run ---------------------------------------
DAILY_BUDGET_USD = float(_env("DAILY_BUDGET_USD", "1.50"))
# the scanner: read the chart for setups the engine does not flag (reversal set ups, 1m plays)
SCAN_MINUTES = int(_env("SCAN_MINUTES", "5"))          # 0 = off
SCAN_WINDOWS = _env("SCAN_WINDOWS", "02:00-04:00,09:25-11:00,13:00-15:00,20:00-22:00")   # ET, per day
SCAN_SHOTS_KEEP_DAYS = int(_env("SCAN_SHOTS_KEEP_DAYS", "14"))   # archived scan screenshots

# --- learning loop ------------------------------------------------------------------------------
MAX_TESTING_HYPOTHESES = int(_env("MAX_TESTING_HYPOTHESES", "8"))
SHADOW_PER_TICK = int(_env("SHADOW_PER_TICK", "3"))        # shadow re-decisions per loop
SHADOW_BACKFILL_DAYS = int(_env("SHADOW_BACKFILL_DAYS", "60"))
MIN_N_FOR_VERDICT = int(_env("MIN_N_FOR_VERDICT", "30"))   # settled trades before a hypothesis is "ready"

# --- dashboard ----------------------------------------------------------------------------------
DASHBOARD_PASSWORD = _env("DASHBOARD_PASSWORD")   # empty = dashboard closed

# --- reporting ----------------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
NOTIFY_SKIPS = _env("NOTIFY_SKIPS", "1") == "1"   # also message skipped setups
LESSONS_IN_PROMPT = int(_env("LESSONS_IN_PROMPT", "20"))
# the built-in one-call lesson per settled trade is OFF now that Hermes reviews every trade;
# its reviews feed the decision prompt instead (set BUILTIN_LESSONS=1 to turn it back on)
BUILTIN_LESSONS = _env("BUILTIN_LESSONS", "0") == "1"
# passages from knowledge/ (full course transcripts, mini lessons, PDFs) added per decision
KNOWLEDGE_PASSAGES = int(_env("KNOWLEDGE_PASSAGES", "6"))

# --- paper only ---------------------------------------------------------------------------------
# There is deliberately no order-placement code in this service. PAPER is informational.
PAPER = True
