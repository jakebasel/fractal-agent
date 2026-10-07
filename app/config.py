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

# --- AI (OpenRouter) ----------------------------------------------------------------------
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
OPENROUTER_URL = _env("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
DECISION_MODEL = _env("DECISION_MODEL", "deepseek/deepseek-chat")   # take/skip + lessons
VISION_MODEL = _env("VISION_MODEL", "google/gemini-2.5-flash")      # reads the screenshot
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
# events that make the whole week demo-only (rule 2.2: CPI/PPI/FOMC week)
NEWS_WEEK_WORDS = [w.strip().lower() for w in _env("NEWS_WEEK_WORDS", "CPI,PPI,FOMC").split(",") if w.strip()]

# --- spend guard: optional work (shadow tests, scanner, Jev backfill) pauses when today's
# OpenRouter spend passes this; live decisions always run ---------------------------------------
DAILY_BUDGET_USD = float(_env("DAILY_BUDGET_USD", "1.50"))
# the scanner: read the chart for setups the engine does not flag (reversal set ups, 1m plays)
SCAN_MINUTES = int(_env("SCAN_MINUTES", "5"))          # 0 = off
SCAN_WINDOWS = _env("SCAN_WINDOWS", "02:00-04:00,09:25-11:00,20:00-22:00")   # ET, per day

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
# passages from knowledge/ (full course transcripts, mini lessons, PDFs) added per decision
KNOWLEDGE_PASSAGES = int(_env("KNOWLEDGE_PASSAGES", "6"))

# --- paper only ---------------------------------------------------------------------------------
# There is deliberately no order-placement code in this service. PAPER is informational.
PAPER = True
