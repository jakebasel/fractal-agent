"""All settings come from environment variables (set them on the wingman app in Coolify)."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _env(name, default=""):
    return os.environ.get(name, default).strip()


DATA_DIR = Path(_env("DATA_DIR", "/data"))

# --- Claude -------------------------------------------------------------------------------
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
ANTHROPIC_URL = _env("ANTHROPIC_URL", "https://api.anthropic.com/v1/messages")
ANTHROPIC_VERSION = _env("ANTHROPIC_VERSION", "2023-06-01")
MODEL = _env("WINGMAN_MODEL", "claude-sonnet-5-5")       # writes the texts and reads screenshots
EFFORT = _env("WINGMAN_EFFORT", "low")
MAX_TOKENS = int(_env("WINGMAN_MAX_TOKENS", "6000"))     # thinking shares this budget
LLM_TIMEOUT_S = float(_env("WINGMAN_LLM_TIMEOUT_S", "120"))

# --- iMessage transport ---------------------------------------------------------------------
# bluebubbles: BlueBubbles Server on a Mac (free; the Mac must stay on and signed in to Messages)
# sendblue:    Sendblue's hosted iMessage API (paid; no Mac)
TRANSPORT = _env("WINGMAN_TRANSPORT", "bluebubbles").lower()
WEBHOOK_TOKEN = _env("WINGMAN_WEBHOOK_TOKEN")             # ?token= on the webhook URL; required
# who may use the bot: phone numbers (+15551234567) or Apple ID emails, comma-separated.
# Empty = the bot replies to the first sender with the handle to put here, and does nothing else.
OWNERS = [h.strip().lower() for h in _env("WINGMAN_OWNER").split(",") if h.strip()]

BB_URL = _env("BB_URL").rstrip("/")                        # e.g. https://xyz.trycloudflare.com
BB_PASSWORD = _env("BB_PASSWORD")
BB_METHOD = _env("BB_METHOD", "apple-script")              # or private-api if enabled on the Mac
# Self-chat mode: the Mac is signed in to YOUR Apple ID and you text yourself. Set this to that
# chat's guid (e.g. iMessage;-;+15551234567); the bot then reads your own messages in that chat
# and marks its replies so it never answers itself.
BB_SELF_CHAT_GUID = _env("BB_SELF_CHAT_GUID")

SB_API_KEY = _env("SB_API_KEY")
SB_API_SECRET = _env("SB_API_SECRET")
SB_FROM_NUMBER = _env("SB_FROM_NUMBER")
SB_URL = _env("SB_URL", "https://api.sendblue.co/api/send-message")

# --- behaviour ------------------------------------------------------------------------------
DEBOUNCE_S = float(_env("WINGMAN_DEBOUNCE_S", "4"))       # gather a screenshot + its caption texts
MAX_PER_DAY = int(_env("WINGMAN_MAX_PER_DAY", "100"))     # Claude calls per ET day
HISTORY_EVENTS = int(_env("WINGMAN_HISTORY", "16"))       # past events per person in the prompt
ABOUT_ME = _env("WINGMAN_ABOUT_ME")                        # default "about me"; the `me:` command overrides
MAX_IMAGE_BYTES = 5_000_000                                # Claude's per-image limit
PENDING_TTL_S = 1800                                       # how long an unnamed read waits for a name
