"""Telegram Q&A: Jake asks a question in the bot chat, Claude answers it with the agent's read-only
tools (the same functions the /mcp connector serves). Paper only: no tool here can place an order.

Telegram -> POST /telegram (secret header) -> a thread runs the tool loop -> sendMessage.
Only TELEGRAM_CHAT_ID gets answers; with it unset the bot replies with the chat id to set."""
import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import config, llm, store

log = logging.getLogger("telegram")

MAX_ROUNDS = 8
TOOL_RESULT_CHARS = 30000
_lock = threading.Lock()

SYSTEM = """You are Jake's trading analyst for the Fractal Agent: a PAPER-only AI filter on top of his
fvg-mcp rules engine (Fractal Effects strategy: Market Translator signals, FVG cascade 5m->1m->30s,
1:3 targets, mainly MNQ1!/MES1!). Jake asks from Telegram on his phone.

Answer from the tools, never from memory: pull the numbers first. How to answer:
- Bottom line first, then the few facts that support it. Short. Plain text only (no markdown,
  no tables, no asterisks); short lines and simple dashes are fine.
- Any results figure carries n, win%, avg R, total R and max drawdown, and names the window.
- Times in ET. Say when n is too small to trust (under ~30 trades).
- Tips must be grounded: cite the rule section, lesson, hypothesis result or trade ids behind
  them. Rule changes are proposals only; Jake approves them on the dashboard.
- This system never places orders. Do not tell Jake to enter or exit a live trade."""

# (tool name, input schema properties, required); descriptions come from the functions' docstrings
_SPECS = [
    ("agent_status", {}, []),
    ("paper_stats", {"days": {"type": "number"}}, []),
    ("symbol_stats", {"days": {"type": "number"}}, []),
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


def tool_defs() -> list:
    fns = _functions()
    return [{"name": name, "description": " ".join((fns[name].__doc__ or name).split()),
             "input_schema": {"type": "object", "properties": props, "required": req}}
            for name, props, req in _SPECS]


def run_tool(name: str, args: dict) -> str:
    fn = _functions().get(name)
    if not fn:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        out = json.dumps(fn(**(args or {})), default=str)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {str(e)[:300]}"})
    return out if len(out) <= TOOL_RESULT_CHARS else out[:TOOL_RESULT_CHARS] + " ...[truncated]"


def secret() -> str:
    return hashlib.sha256(("telegram|" + config.TELEGRAM_BOT_TOKEN).encode()).hexdigest()[:48]


def _api(method: str, **params) -> dict:
    r = httpx.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}", json=params, timeout=20)
    return r.json()


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


def answer(question: str, history: list) -> str:
    """The tool loop. history: past {"role", "content": str} turns, oldest first."""
    messages = history + [{"role": "user", "content": question}]
    tools = tool_defs()
    for _ in range(MAX_ROUNDS):
        data = llm.chat_with_tools(config.TELEGRAM_MODEL, SYSTEM, messages, tools, max_tokens=16000,
                                   effort=config.TELEGRAM_EFFORT, purpose="telegram")
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


def handle(chat_id, text: str):
    hkey = f"tg_history:{chat_id}"
    cmd = text.strip().split()[0].lower() if text.strip() else ""
    if cmd in ("/start", "/help"):
        send(chat_id, "Ask me about the paper agent: today's results, which symbols pay, why a trade "
                      "was skipped, open hypotheses, what the rules say. /reset clears the conversation.")
        return
    if cmd == "/reset":
        store.kv_set(hkey, [])
        send(chat_id, "Conversation cleared.")
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
    try:
        reply = answer(text[:4000], history)
    except Exception as e:
        log.exception("telegram answer failed")
        send(chat_id, f"Error answering: {str(e)[:300]}")
        return
    send(chat_id, reply)
    keep = max(0, config.TELEGRAM_HISTORY)
    store.kv_set(hkey, (history + [{"role": "user", "content": text[:4000]},
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
    chat_id, text = (msg.get("chat") or {}).get("id"), msg.get("text") or ""
    if chat_id is None or not text:
        return JSONResponse({"ok": True})
    if not config.TELEGRAM_CHAT_ID:
        threading.Thread(target=send, args=(chat_id, f"Your chat id is {chat_id}. Set TELEGRAM_CHAT_ID to it "
                                                     "on the fractal-agent app in Coolify, then redeploy."),
                         daemon=True).start()
        return JSONResponse({"ok": True})
    if str(chat_id) != config.TELEGRAM_CHAT_ID:
        return JSONResponse({"ok": True})
    threading.Thread(target=handle, args=(chat_id, text), daemon=True, name="tg-answer").start()
    return JSONResponse({"ok": True})
