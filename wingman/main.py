"""Wingman webhook app. iMessage -> POST /webhook?token=... -> buffered for a few seconds (so a
screenshot and the text after it arrive as one request) -> a thread runs commands or one Claude
call -> replies go back as separate bubbles, one per suggested text, so each copies cleanly.

Only WINGMAN_OWNER may use it. With it unset, the bot answers the first sender with the handle
to set and does nothing else."""
import collections
import hashlib
import hmac
import logging
import re
import threading
import time
from datetime import datetime

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import brain, config, store, transport

log = logging.getLogger("wingman")
T = transport.get()

_buf_lock = threading.Lock()
_buffers: dict = {}                       # chat -> {"texts", "atts", "timer"}
_chat_locks: dict = {}
_seen = collections.deque(maxlen=1000)    # message guids already handled
_sent = collections.deque(maxlen=200)     # hashes of our own texts (self-chat mode echo guard)

HELP = """Wingman - send me:
- a screenshot of a chat or profile (add a name or a note if you like)
- a name ("sarah?") for the next text in that thread
- a question ("she left me on read, now what")

Commands:
list - everyone and where it stands
info sarah - what I know about her
note sarah: works in PR, loves tequila
sent 2 - log which option you sent (or sent: <what you actually wrote>)
use sarah - switch who follow-ups are about
me: <about you: city, job, go-to bars, how you text>
forget sarah"""


# ---------------------------------------------------------------- sending
def _h(text: str) -> str:
    return hashlib.sha1(text.strip().encode()).hexdigest()


def send(chat: str, text: str):
    text = (text or "").strip()
    if not text:
        return
    _sent.append(_h(text))   # before sending: the echo can beat the HTTP response
    T.send(chat, text)


# ---------------------------------------------------------------- inbound
def norm(handle: str) -> str:
    h = str(handle or "").strip().lower()
    if "@" in h:
        return h
    d = re.sub(r"\D", "", h)
    return d[-10:] if len(d) >= 10 else d


def is_owner(sender: str) -> bool:
    return norm(sender) in {norm(o) for o in config.OWNERS}


def accept(m: transport.Inbound):
    if not m.guid or m.guid in _seen:
        return
    _seen.append(m.guid)
    if m.from_me:
        # only in self-chat mode, only in that chat, and never our own replies
        if not (config.BB_SELF_CHAT_GUID and m.chat == config.BB_SELF_CHAT_GUID) or _h(m.text) in _sent:
            return
    elif not config.OWNERS:
        threading.Thread(target=send, daemon=True, args=(
            m.chat, f"Your handle is {m.sender}. Set WINGMAN_OWNER={m.sender} on the wingman app, "
                    "then redeploy.")).start()
        return
    elif not is_owner(m.sender):
        return
    if not (m.text or m.attachments):
        return
    enqueue(m)


def enqueue(m: transport.Inbound):
    if config.DEBOUNCE_S <= 0:
        process(m.chat, [m.text] if m.text else [], list(m.attachments))
        return
    with _buf_lock:
        b = _buffers.setdefault(m.chat, {"texts": [], "atts": [], "timer": None})
        if m.text:
            b["texts"].append(m.text)
        b["atts"].extend(m.attachments)
        if b["timer"]:
            b["timer"].cancel()
        t = threading.Timer(config.DEBOUNCE_S, _flush, args=(m.chat,))
        t.daemon = True
        b["timer"] = t
        t.start()


def _flush(chat: str):
    with _buf_lock:
        b = _buffers.pop(chat, None)
    if b:
        process(chat, b["texts"], b["atts"])


def process(chat: str, texts: list, atts: list):
    with _chat_locks.setdefault(chat, threading.Lock()):
        try:
            _process(chat, texts, atts)
        except Exception as e:
            log.exception("wingman failed")
            try:
                send(chat, f"Wingman hit an error: {str(e)[:200]}")
            except Exception:
                pass


# ---------------------------------------------------------------- commands
def _active():
    pid = store.kv_get("active")
    return store.get(pid) if pid else None


def _profile(p: dict) -> str:
    sugg = store.last_suggestions(p["id"])
    return (f"{p['name']} - {(p['stage'] or '?').replace('_', ' ')}\n{p['summary'] or ''}\n\n"
            f"Notes:\n{p['notes'] or '-'}"
            + ("\n\nLast suggestions:\n" + "\n".join(f"#{i + 1} {s}" for i, s in enumerate(sugg)) if sugg else ""))


def command(chat: str, text: str) -> bool:
    t = text.strip()
    low = t.lower()
    word = re.split(r"[\s:]+", low)[0].lstrip("/") if low else ""
    rest = t[len(t.split()[0]):].strip() if t else ""
    if low in ("help", "?", "/help", "commands"):
        send(chat, HELP)
        return True
    if low in ("list", "who", "roster", "/list"):
        ps = store.people()
        send(chat, "\n".join(f"- {p['name']}: {(p['stage'] or '?').replace('_', ' ')} - {p['summary'] or ''}"
                             for p in ps) or "Nobody yet. Send me a screenshot.")
        return True
    if word == "me" and (low == "me" or low.startswith("me:")):
        about = t.split(":", 1)[1].strip() if ":" in t else ""
        if about:
            store.kv_set("about_me", about)
            send(chat, "Got it. I'll write like that and only use those facts about you.")
        else:
            send(chat, "About you:\n" + brain.about_me())
        return True
    if word in ("forget", "delete") and rest:
        p = store.find(rest)
        if not p:
            send(chat, f"I don't have anyone called {rest}.")
        else:
            store.forget(p["id"])
            send(chat, f"Forgot {p['name']}.")
        return True
    if word in ("info", "show") and rest:
        p = store.find(rest)
        send(chat, _profile(p) if p else f"I don't have anyone called {rest}.")
        return True
    if word in ("use", "switch") and rest:
        p = store.find(rest)
        if p:
            store.kv_set("active", p["id"])
        send(chat, f"Now on {p['name']}." if p else f"I don't have anyone called {rest}.")
        return True
    m = re.match(r"(?is)^note\s+(.+?)\s*:\s*(.+)$", t)
    if m:
        p = store.find(m.group(1)) or store.create(m.group(1).strip().title())
        store.add_notes(p["id"], [m.group(2)])
        store.add_event(p["id"], "note", m.group(2))
        send(chat, f"Noted for {p['name']}.")
        return True
    m = re.match(r"(?is)^sent\s*(?:#?(\d)\b|:\s*(.+))?\s*$", t)
    if m:
        p = _active()
        if not p:
            send(chat, "Sent to who? `use <name>` first.")
            return True
        if m.group(2):
            what = m.group(2).strip()
        else:
            sugg = store.last_suggestions(p["id"])
            i = int(m.group(1) or 1) - 1
            if not (0 <= i < len(sugg)):
                send(chat, f"I don't have option #{i + 1} for {p['name']}.")
                return True
            what = sugg[i]
        store.add_event(p["id"], "sent", what)
        send(chat, f"Logged for {p['name']}. Send me her reply when it comes.")
        return True
    return False


# ---------------------------------------------------------------- the Claude path
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{0,29}$")


def _mentioned(text: str):
    """A known person named in the text (by full name or first name), if exactly one is."""
    low = text.lower()
    hits = []
    for p in store.people():
        names = {p["key"], p["key"].split()[0]}
        if any(re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", low) for n in names if len(n) >= 2):
            hits.append(p)
    return hits[0] if len(hits) == 1 else None


def _count_ok() -> bool:
    k = "count:" + datetime.now(config.ET).strftime("%Y-%m-%d")
    n = int(store.kv_get(k) or 0)
    if n >= config.MAX_PER_DAY:
        return False
    store.kv_set(k, n + 1)
    return True


def suggestions(res: dict) -> list:
    out = list(res["replies"])
    if res["ask"] and res["ask"] not in out:
        out.append(res["ask"])
    return out


def save(p: dict, text: str, had_images: bool, res: dict):
    pid = p["id"]
    if text or had_images:
        store.add_event(pid, "jake", ("[screenshot] " if had_images else "") + (text or ""))
    if res["transcript"]:
        store.add_event(pid, "convo", res["transcript"])
    if suggestions(res):
        store.add_event(pid, "suggestion", suggestions(res))
    store.add_notes(pid, res["notes_add"])
    store.update(pid, **{k: res[k] for k in ("stage", "summary") if res[k]})
    store.kv_set("active", pid)


def bubbles(name: str | None, res: dict) -> list:
    head = []
    if name:
        head.append(name + (f" - {res['stage'].replace('_', ' ')}" if res["stage"] else ""))
    for k in ("read", "message"):
        if res[k]:
            head.append(res[k])
    if res["tip"]:
        head.append("Tip: " + res["tip"])
    sugg = suggestions(res)
    if sugg:
        legend = f"{len(sugg)} options below"
        if res["ask"]:
            legend += f", #{len(sugg)} is the ask"
        head.append(legend + ". Reply \"sent 2\" when you send one.")
    if not name:
        head.append("Who's this? Reply with her name and I'll save it.")
    return ["\n".join(head)] + sugg


def _process(chat: str, texts: list, atts: list):
    text = "\n".join(t for t in texts if t).strip()
    if not atts and len(texts) == 1 and command(chat, text):
        return
    pend = store.kv_get("pending")
    if pend and not atts and NAME_RE.match(text) and time.time() - pend["at"] < config.PENDING_TTL_S:
        p = store.find(text) or store.create(text.strip().title())
        save(p, pend["text"], pend["had_images"], pend["res"])
        store.kv_set("pending", None)
        send(chat, f"Saved under {p['name']}.")
        return
    images = []
    for ref in atts[:4]:
        b = T.fetch(ref)
        if not brain.mime(b):
            send(chat, "I can't read that image format. Send a screenshot (PNG/JPEG) instead.")
        elif len(b) > config.MAX_IMAGE_BYTES:
            send(chat, "That image is over 5 MB. Send a screenshot instead of the original photo.")
        else:
            images.append(b)
    if atts and not images and not text:
        return
    if not _count_ok():
        send(chat, f"Daily limit reached ({config.MAX_PER_DAY}). Raise WINGMAN_MAX_PER_DAY to allow more.")
        return
    person = _mentioned(text) or _active()
    res = brain.think(text, images, person)
    p = None
    if res["person"]:
        p = store.find(res["person"])
        if not p and person and store.key(res["person"]).split()[0] == person["key"].split()[0]:
            p = person
        p = p or store.create(res["person"])
        save(p, text, bool(images), res)
        store.kv_set("pending", None)
    else:
        store.kv_set("pending", {"at": time.time(), "text": text, "had_images": bool(images), "res": res})
    for b in bubbles(p["name"] if p else None, res):
        send(chat, b)


# ---------------------------------------------------------------- HTTP
async def webhook(request: Request):
    tok = request.query_params.get("token", "")
    if not config.WEBHOOK_TOKEN or not hmac.compare_digest(tok.encode(), config.WEBHOOK_TOKEN.encode()):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse({"ok": True})
    for m in T.parse(payload):
        accept(m)
    return JSONResponse({"ok": True})


async def health(request: Request):
    return JSONResponse({"ok": True, "transport": T.name, "model": config.MODEL,
                         "key_set": bool(config.ANTHROPIC_API_KEY), "owner_set": bool(config.OWNERS),
                         "token_set": bool(config.WEBHOOK_TOKEN), "self_chat": bool(config.BB_SELF_CHAT_GUID),
                         "people": len(store.people())})


logging.basicConfig(level=logging.INFO)
app = Starlette(routes=[Route("/health", health), Route("/webhook", webhook, methods=["POST"])])
