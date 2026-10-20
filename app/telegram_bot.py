"""Telegram Q&A: Jake asks a question or posts a chart screenshot in the bot chat; Claude answers
with the rulebook in its prompt and two read-only tool sets: the paper agent's own (the same
functions /mcp serves: stats, decisions, lessons, hypotheses, course + live-session search) and
fvg-mcp's (live setups, entries, Market Translator events, FVGs, trade history), prefixed fvg_.
Paper only: no tool here can place an order.

Telegram -> POST /telegram (secret header) -> a thread runs the tool loop -> sendMessage.
Only TELEGRAM_CHAT_ID gets answers; with it unset the bot replies with the chat id to set."""
import base64
import hashlib
import hmac
import json
import logging
import re
import threading
import time
from datetime import datetime

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import config, llm, prompts, store
from .mcp_client import FVG

log = logging.getLogger("telegram")

MAX_ROUNDS = 10
TOOL_RESULT_CHARS = 30000
FVG_PREFIX = "fvg_"
FVG_TOOLS_TTL_S = 600
MAX_IMAGE_BYTES = 8_000_000
_lock = threading.Lock()
_fvg_cache = {"at": 0.0, "tools": []}

SYSTEM = """You are Jake's trading analyst for the Fractal Effects futures strategy (Market Translator
and Spotlight indicators; FVG cascade 5m->1m->30s; 1:3 targets). Jake asks from Telegram on his
phone, sometimes with a TradingView screenshot.

Your sources, in priority order on a conflict: amendments > rulebook > live-session rules (all
three are below) > course and live-session passages (knowledge_search, instructor_calls) >
lessons and reviews from past paper trades.

Tools:
- The paper agent: paper_stats, symbol_stats, strategy_report, decisions, decision_detail,
  lessons, hypotheses, reviews, pending_setups, spotted_setups, chart_question, api_spend.
- The live rules engine (fvg-mcp, tools prefixed fvg_): live setups, engine entries, Market
  Translator signals, active FVGs, confluence, trade history per symbol.
- knowledge_search: the 9 course modules, mini lessons, SOP and live-session transcripts. Use it
  to quote the instructor when a call depends on his teaching.

Coverage: the paper agent itself only decides {agent_symbols} (the Fusion Markets CFDs
on Jake's chart layout), but fvg-mcp tracks ~150 futures and CFD symbols. Never say only those are tracked. For "what is setting up now / best trade" questions:
fvg_recent_events(source="market_translator", limit=40) for fresh signals on every symbol and
fvg_entries(limit=30) for the newest validated entries; rank the candidates with symbol_stats
(which symbols pay for the core strategy); then fvg_setups(symbol) on the best 3-5 for stage,
entry, stop, target. Jake may use CFD names: NAS100=NQ/MNQ, US500=ES/MES, US30=YM/MYM, US2000=RTY/M2K,
XAUUSD=GC/MGC, XAGUSD=SI/SIL, USOIL=CL/MCL, GER40=FDAX, EURUSD=6E, GBPUSD=6B, USDJPY=6J (inverse).
Some CFD symbols (e.g. US500) have their own feed in fvg-mcp: try the CFD name itself first.

Progress, performance or "what should we change": call hypotheses (each has same-trade books vs
the agent and core, the trades it changed, and a written case with a recommendation) plus
paper_stats and trade_breakdown. Lead with which hypotheses to approve, reject or keep watching
and why, then which entry types or assets to skip, each with its numbers. Hypotheses sourced
"instructor-conflict" test the instructor's live-session teaching against the written rules.

Winners vs losers / which entries to skip: call trade_breakdown(symbol, days). Never tally a
trade list by hand. Report the worst and best buckets, and a bucket whose share of the losses
is well above its share of the wins as a skip candidate, with its n.

With a screenshot: read it first (symbol, timeframe, last price, M/2M/DB/2DB signals and white
lines and whether a body closed through them, FVGs, reversal zones, purple/blue zones, NDOG/NWOG,
Spotlight DR box and confirmation, EMAs 20/238, trend table, structure). Say what is not visible
instead of guessing. Then check the live engine for that symbol (fvg_ setups / recent events) and
judge it against the rules: which play this is, must-haves present or missing, boosters, hard
rules, grade, where it is invalidated, what has to happen next before it is valid.

How to answer:
- Bottom line first, then the facts behind it. Short. Plain text only (no markdown, no tables,
  no asterisks); short lines and dashes are fine.
- Results figures carry n, win%, avg R, total R and max drawdown, and name the window. Say when n
  is too small to trust (under ~30).
- Times in ET. Cite rule sections (e.g. §2.6), trade ids or the course module behind a tip.
- Rule changes are proposals; Jake approves them on the dashboard. This system is paper only:
  describe what the rules say about a setup, never tell Jake to place, size or exit a live order.

=== RULES ===
--- amendments.md ---
{amendments}
--- rulebook.md ---
{rulebook}
--- live_rules.md ---
{live_rules}"""


def system_prompt() -> str:
    return SYSTEM.format(amendments=prompts._read("amendments.md"), rulebook=prompts._read("rulebook.md"),
                         live_rules=prompts._read("live_rules.md"),
                         agent_symbols=", ".join(config.SYMBOLS))


# (tool name, input schema properties, required); descriptions come from the functions' docstrings
_SPECS = [
    ("agent_status", {}, []),
    ("paper_stats", {"days": {"type": "number"}}, []),
    ("symbol_stats", {"days": {"type": "number"}}, []),
    ("trade_breakdown", {"symbol": {"type": "string"}, "days": {"type": "number"}}, []),
    ("strategy_report", {"days": {"type": "number"}}, []),
    ("decisions", {"limit": {"type": "integer"}, "symbol": {"type": "string"}}, []),
    ("decision_detail", {"entry_id": {"type": "integer"}}, ["entry_id"]),
    ("lessons", {"limit": {"type": "integer"}}, []),
    ("hypotheses", {}, []),
    ("reviews", {"limit": {"type": "integer"}, "entry_id": {"type": "integer"}}, []),
    ("pending_setups", {}, []),
    ("spotted_setups", {"limit": {"type": "integer"}}, []),
    ("rules_text", {"which": {"type": "string", "enum": ["all", "amendments", "rulebook", "live_rules"]}}, []),
    ("knowledge_search", {"query": {"type": "string"}, "k": {"type": "integer"}}, ["query"]),
    ("instructor_calls", {}, []),
    ("chart_question", {"entry_id": {"type": "integer"}, "question": {"type": "string"},
                        "at": {"type": "string", "enum": ["decision", "exit"]}}, ["entry_id", "question"]),
    ("api_spend", {"days": {"type": "number"}}, []),
]


def _functions() -> dict:
    from . import main   # late import: main imports this module
    return {name: getattr(main, name) for name, _, _ in _SPECS}


def _fvg_tools() -> list:
    """fvg-mcp's tool list (its MCP is read-only), cached; empty if it is unreachable."""
    if time.time() - _fvg_cache["at"] < FVG_TOOLS_TTL_S:
        return _fvg_cache["tools"]
    try:
        tools = FVG().list_tools()
    except Exception as e:
        log.warning("fvg-mcp tools/list failed: %s", e)
        tools = _fvg_cache["tools"]
    _fvg_cache.update(at=time.time(), tools=tools)
    return tools


def tool_defs() -> list:
    fns = _functions()
    out = [{"name": name, "description": " ".join((fns[name].__doc__ or name).split()),
            "input_schema": {"type": "object", "properties": props, "required": req}}
           for name, props, req in _SPECS]
    for t in _fvg_tools():
        schema = t.get("inputSchema") or {"type": "object", "properties": {}}
        out.append({"name": FVG_PREFIX + t["name"],
                    "description": "Live rules engine (fvg-mcp): " + " ".join((t.get("description") or t["name"]).split())[:1000],
                    "input_schema": {"type": "object", "properties": schema.get("properties") or {},
                                     "required": schema.get("required") or []}})
    return out


def run_tool(name: str, args: dict) -> str:
    try:
        if name.startswith(FVG_PREFIX):
            res = FVG().call(name[len(FVG_PREFIX):], **(args or {}))
        else:
            fn = _functions().get(name)
            if not fn:
                return json.dumps({"error": f"unknown tool {name}"})
            res = fn(**(args or {}))
        out = json.dumps(res, default=str)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {str(e)[:300]}"})
    return out if len(out) <= TOOL_RESULT_CHARS else out[:TOOL_RESULT_CHARS] + " ...[truncated]"


def secret() -> str:
    return hashlib.sha256(("telegram|" + config.TELEGRAM_BOT_TOKEN).encode()).hexdigest()[:48]


# ---- Zoom Trade Alerts relay (2026-10-20) ------------------------------------------------
# Jake deleted the Zoom bot and asked for its commands on this one. This bot receives by
# webhook, and Telegram allows a bot only one delivery mode, so the Mac (zoom-trade-alerts)
# can't poll getUpdates for it. Instead Zoom messages are queued here and the Mac pulls
# them from GET /zoom/inbox; it still SENDS transcripts and alerts straight to Telegram.
ZOOM_CMDS = {"/join", "/listen", "/stop", "/leave", "/live", "/livetext", "/transcript",
             "/last", "/record", "/recordings", "/status", "/test"}
ZOOM_LINK_RE = re.compile(r"(?:https?://)?[\w.-]*zoom(?:gov)?\.(?:us|com)/[^\s<>\"')]+", re.I)
ANY_LINK_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
ZOOM_QUEUE_MAX = 50
ZOOM_MAC_STALE_S = 30        # no inbox poll for this long = the Mac app isn't running
_zoom_lock = threading.Lock()


def zoom_token() -> str:
    """Shared with the Mac without a new secret: both sides hold the bot token."""
    return hashlib.sha256(("zoom|" + config.TELEGRAM_BOT_TOKEN).encode()).hexdigest()[:48]


def is_zoom_message(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t.split()[0].lower().split("@")[0] in ZOOM_CMDS or ZOOM_LINK_RE.search(t):
        return True
    # "/join" with no link makes the Mac ask for one; the reply is any link (Meet, YouTube...)
    return bool(ANY_LINK_RE.search(t)) and time.time() < float(store.kv_get("zoom_wait_link_until") or 0)


def zoom_enqueue(msg: dict) -> None:
    text = (msg.get("text") or msg.get("caption") or "").strip()
    with _zoom_lock:
        seq = int(store.kv_get("zoom_seq") or 0) + 1
        queue = (store.kv_get("zoom_queue") or [])[-(ZOOM_QUEUE_MAX - 1):]
        queue.append({"seq": seq, "at": time.time(), "message": msg})
        store.kv_set("zoom_seq", seq)
        store.kv_set("zoom_queue", queue)
        if text.lower().startswith("/join") and not ANY_LINK_RE.search(text):
            store.kv_set("zoom_wait_link_until", time.time() + 300)
        elif ANY_LINK_RE.search(text):
            store.kv_set("zoom_wait_link_until", 0)
    if time.time() - float(store.kv_get("zoom_last_poll") or 0) > ZOOM_MAC_STALE_S:
        send(msg["chat"]["id"], "Zoom Trade Alerts isn't running on the Mac. Double-click start.command "
                                "there; it'll pick this up if you start it within 15 minutes.")


async def zoom_inbox(request: Request):
    got = request.headers.get("x-zoom-token", "")
    if not config.TELEGRAM_BOT_TOKEN or not hmac.compare_digest(got.encode(), zoom_token().encode()):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        after = int(request.query_params.get("after") or 0)
    except ValueError:
        after = 0
    store.kv_set("zoom_last_poll", time.time())
    items = [x for x in (store.kv_get("zoom_queue") or []) if x["seq"] > after]
    return JSONResponse({"items": items, "seq": int(store.kv_get("zoom_seq") or 0)})


def _api(method: str, **params) -> dict:
    r = httpx.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}", json=params, timeout=20)
    return r.json()


def _download(file_id: str) -> bytes:
    info = _api("getFile", file_id=file_id)
    path = (info.get("result") or {}).get("file_path")
    if not path:
        raise RuntimeError(f"getFile failed: {info.get('description')}")
    r = httpx.get(f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/{path}", timeout=30)
    r.raise_for_status()
    return r.content


def register_webhook():
    try:
        res = _api("setWebhook", url=config.PUBLIC_URL + "/telegram", secret_token=secret(),
                   allowed_updates=["message"], drop_pending_updates=True)
        log.info("telegram setWebhook: %s", res.get("description") or res.get("ok"))
    except Exception as e:
        log.warning("telegram setWebhook failed: %s", e)


def send(chat_id, text: str):
    text = text.strip() or "(no answer)"
    for i in range(0, len(text), 4000):
        _api("sendMessage", chat_id=chat_id, text=text[i:i + 4000], disable_web_page_preview=True)


MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}


def default_model() -> str:
    return store.kv_get("tg_model") or config.TELEGRAM_MODEL


def answer(question, history: list, model: str | None = None, effort: str | None = None) -> str:
    """The tool loop. question: text, or content blocks (image + text). history: past
    {"role", "content": str} turns, oldest first."""
    messages = history + [{"role": "user", "content": question}]
    tools, system = tool_defs(), system_prompt()
    model, effort = model or default_model(), effort or config.TELEGRAM_EFFORT
    for _ in range(MAX_ROUNDS):
        data = llm.chat_with_tools(model, system, messages, tools, max_tokens=16000,
                                   effort=effort, purpose="telegram")
        content = data.get("content") or []
        calls = [b for b in content if b.get("type") == "tool_use"]
        if data.get("stop_reason") != "tool_use" or not calls:
            return "".join(b.get("text") or "" for b in content if b.get("type") == "text")
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b["id"], "content": run_tool(b["name"], b.get("input") or {})}
            for b in calls]})
    return "I hit the tool-call limit before finishing. Ask a narrower question."


def _today_key() -> str:
    return "tg_count:" + datetime.now(config.ET).strftime("%Y-%m-%d")


def _image_file_id(msg: dict) -> str | None:
    if msg.get("photo"):
        return max(msg["photo"], key=lambda p: p.get("file_size") or p.get("width", 0) * p.get("height", 0))["file_id"]
    doc = msg.get("document") or {}
    if str(doc.get("mime_type", "")).startswith("image/"):
        return doc["file_id"]
    return None


def handle(chat_id, text: str, image_id: str | None = None):
    hkey = f"tg_history:{chat_id}"
    cmd = text.strip().split()[0].lower() if text.strip() and not image_id else ""
    if cmd in ("/start", "/help"):
        send(chat_id, "Ask me about the paper agent or the live engine, or send a chart screenshot "
                      "(add a question as the caption).\n/deep <question> - one answer from the stronger "
                      f"model ({config.TELEGRAM_DEEP_MODEL})\n/model haiku|sonnet|opus - change the default "
                      f"(now {default_model()})\n/reset - clear the conversation\n\n"
                      "Zoom (runs on the Mac): paste a Zoom link, or /join, /listen, /stop, /leave, "
                      "/live, /last 5, /record, /recordings, /status, /test")
        return
    if cmd == "/reset":
        store.kv_set(hkey, [])
        send(chat_id, "Conversation cleared.")
        return
    model = effort = None
    if cmd == "/model":
        # "/model opus" changes the default; "/model opus <question>" uses it for that question only
        parts = text.strip().split(maxsplit=2)
        arg = parts[1].lower() if len(parts) > 1 else ""
        text = parts[2] if len(parts) > 2 and arg in MODELS else ""
        if not text and not image_id:
            if arg in MODELS:
                store.kv_set("tg_model", MODELS[arg])
            send(chat_id, f"Default model: {default_model()}. Options: {', '.join(MODELS)}.")
            return
        if arg in MODELS:
            model = MODELS[arg]
            effort = config.TELEGRAM_DEEP_EFFORT if arg != "haiku" else None
    if cmd == "/deep" or (image_id and text.strip().lower().startswith("/deep")):
        model, effort = config.TELEGRAM_DEEP_MODEL, config.TELEGRAM_DEEP_EFFORT
        text = text.strip()[5:].strip()
        if not text and not image_id:
            send(chat_id, "Usage: /deep <question>")
            return
    with _lock:
        n = int(store.kv_get(_today_key()) or 0)
        if n >= config.TELEGRAM_MAX_PER_DAY:
            send(chat_id, f"Daily limit reached ({config.TELEGRAM_MAX_PER_DAY} questions). Raise TELEGRAM_MAX_PER_DAY to allow more.")
            return
        store.kv_set(_today_key(), n + 1)
    try:
        _api("sendChatAction", chat_id=chat_id, action="typing")
    except Exception:
        pass
    history = store.kv_get(hkey) or []
    text = text[:4000]
    try:
        if image_id:
            img = _download(image_id)
            if len(img) > MAX_IMAGE_BYTES:
                send(chat_id, "That image is too large. Send it as a photo instead of a file.")
                return
            media = "image/png" if img[:4] == b"\x89PNG" else "image/jpeg"
            question = [{"type": "image", "source": {"type": "base64", "media_type": media,
                                                     "data": base64.b64encode(img).decode()}},
                        {"type": "text", "text": text or "Analyse this chart against the rules."}]
        else:
            question = text
        reply = answer(question, history, model, effort)
    except Exception as e:
        log.exception("telegram answer failed")
        send(chat_id, f"Error answering: {str(e)[:300]}")
        return
    send(chat_id, reply)
    keep = max(0, config.TELEGRAM_HISTORY)
    asked = ("[screenshot] " if image_id else "") + text
    store.kv_set(hkey, (history + [{"role": "user", "content": asked},
                                   {"role": "assistant", "content": reply[:4000]}])[-keep:] if keep else [])


async def webhook(request: Request):
    if not config.TELEGRAM_BOT_TOKEN:
        return JSONResponse({"error": "telegram not configured"}, status_code=404)
    got = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(got.encode(), secret().encode()):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        update = await request.json()
    except ValueError:
        return JSONResponse({"ok": True})
    with _lock:   # Telegram re-sends an update it thinks failed; answer each once
        uid = update.get("update_id") or 0
        if uid and uid <= int(store.kv_get("tg_last_update") or 0):
            return JSONResponse({"ok": True})
        store.kv_set("tg_last_update", uid)
    msg = update.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    text, image_id = msg.get("text") or msg.get("caption") or "", _image_file_id(msg)
    if chat_id is None or not (text or image_id):
        return JSONResponse({"ok": True})
    if not config.TELEGRAM_CHAT_ID:
        threading.Thread(target=send, args=(chat_id, f"Your chat id is {chat_id}. Set TELEGRAM_CHAT_ID to it "
                                                     "on the fractal-agent app in Coolify, then redeploy."),
                         daemon=True).start()
        return JSONResponse({"ok": True})
    if str(chat_id) != config.TELEGRAM_CHAT_ID:
        return JSONResponse({"ok": True})
    if not image_id and is_zoom_message(text):
        threading.Thread(target=zoom_enqueue, args=(msg,), daemon=True, name="tg-zoom").start()
        return JSONResponse({"ok": True})
    threading.Thread(target=handle, args=(chat_id, text, image_id), daemon=True, name="tg-answer").start()
    return JSONResponse({"ok": True})
