"""Wingman (iMessage dating wingman) with a fake Claude and a fake iMessage transport.

Run:  python3 tests/test_wingman.py
No network, no API spend."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.update(DATA_DIR=tempfile.mkdtemp(), WINGMAN_TRANSPORT="bluebubbles", WINGMAN_WEBHOOK_TOKEN="tok",
                  WINGMAN_OWNER="+1 (555) 000-1111", WINGMAN_DEBOUNCE_S="0", ANTHROPIC_API_KEY="test",
                  BB_URL="http://mac", BB_PASSWORD="pw", WINGMAN_ABOUT_ME="Jake, Miami, trader")

from starlette.testclient import TestClient  # noqa: E402

from wingman import brain, config, main, store, transport  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
HEIC = b"\x00\x00\x00\x18ftypheic" + b"0" * 50
SENT, CALLS, REPLIES = [], [], []


def fake_send(chat, text):
    SENT.append((chat, text))


def fake_claude(system, content):
    CALLS.append(content)
    return REPLIES.pop(0) if REPLIES else json.dumps({"person": None, "replies": []})


main.T.send = fake_send
main.T.fetch = lambda ref: {"att-png": PNG, "att-heic": HEIC}[ref]
brain.call_claude = fake_claude
client = TestClient(main.app)
FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


_n = [0]


def bb(text="", atts=(), sender="+15550001111", from_me=False, chat="iMessage;-;+15550001111", guid=None):
    _n[0] += 1
    return {"type": "new-message", "data": {
        "guid": guid or f"g{_n[0]}", "text": text, "isFromMe": from_me, "handle": {"address": sender},
        "chats": [{"guid": chat}], "attachments": [{"guid": a, "mimeType": "image/png"} for a in atts]}}


def post(payload, token="tok"):
    SENT.clear()
    return client.post(f"/webhook?token={token}", json=payload)


def reply(**kw):
    base = {"person": None, "transcript": [], "stage": "", "read": "", "replies": [], "ask": "", "tip": "",
            "notes_add": [], "summary": "", "message": ""}
    base.update(kw)
    REPLIES.append("Here you go:\n```json\n" + json.dumps(base) + "\n```")


# ---- auth and who may use it
r = post(bb("hi"), token="nope")
check("wrong token -> 401", r.status_code == 401)
post(bb("hi", sender="+15559998888", chat="iMessage;-;+15559998888"))
check("a stranger gets nothing and costs nothing", not SENT and not CALLS)
post(bb("hi", from_me=True))
check("my own outgoing messages are ignored (no self-chat mode)", not SENT and not CALLS)
check("owner match ignores formatting", main.is_owner("+15550001111") and main.is_owner("5550001111"))

# ---- screenshot + caption -> person created, one bubble per option
reply(person="Sarah", stage="ready_to_ask", read="Warm: she asks questions back and replies fast.",
      transcript=[{"from": "her", "text": "haha you surf?"}, {"from": "jake", "text": "badly"}],
      replies=["badly but with conviction", "only when no one's watching", "teach me something then"],
      ask="drinks thursday? I know a mezcal spot", tip="Ask tonight while it's moving.",
      notes_add=["surfs", "from Hinge"], summary="Joking about surfing, she's engaged")
post(bb("sarah from hinge", atts=["att-png"]))
content = CALLS[-1]
check("screenshot goes to Claude as an image block", content[0]["type"] == "image"
      and content[0]["source"]["media_type"] == "image/png")
ctx = content[-1]["text"]
check("prompt carries about-me, the time in ET and the caption",
      "Jake, Miami, trader" in ctx and " ET" in ctx and "sarah from hinge" in ctx)
check("5 bubbles: header + 3 replies + the ask", len(SENT) == 5, [t for _, t in SENT])
check("header has name, stage, read, tip and the legend",
      SENT[0][1].startswith("Sarah - ready to ask") and "Warm" in SENT[0][1] and "Tip:" in SENT[0][1]
      and "#4 is the ask" in SENT[0][1])
check("each option is its own clean bubble", SENT[1][1] == "badly but with conviction"
      and SENT[4][1] == "drinks thursday? I know a mezcal spot")
check("replies go to the chat they came from", all(c == "iMessage;-;+15550001111" for c, _ in SENT))
p = store.find("sarah")
check("Sarah saved with stage, summary, notes", p and p["stage"] == "ready_to_ask"
      and "surfs" in p["notes"] and p["summary"].startswith("Joking"))
kinds = [e["kind"] for e in store.events(p["id"])]
check("thread logged: request, conversation, suggestions", kinds == ["jake", "convo", "suggestion"], kinds)

# ---- follow-ups use what we know
post(bb("sent 4"))
ev = store.events(p["id"])[-1]
check("'sent 4' logs the ask as sent", ev["kind"] == "sent" and ev["content"].startswith("drinks thursday"))
reply(person="Sarah", stage="asked", read="Waiting on her.", message="Give it a few hours.")
post(bb("she hasn't answered, now what"))
ctx = CALLS[-1][-1]["text"]
check("follow-up without a name uses the active person's thread",
      "ACTIVE PERSON: Sarah" in ctx and "Jake SENT: drinks thursday" in ctx and "her: haha you surf?" in ctx)
check("question answered in the header, no option bubbles", len(SENT) == 1 and "few hours" in SENT[0][1])

# ---- unnamed screenshot -> asks who, then binds to the name
reply(person=None, stage="opener", read="Profile: likes hiking.", replies=["opener a", "opener b"],
      notes_add=["hikes"])
post(bb("", atts=["att-png"]))
check("unknown person: asks who it is", "Who's this?" in SENT[0][1] and len(SENT) == 3)
n_calls = len(CALLS)
post(bb("Emma"))
e = store.find("emma")
check("replying a name saves the pending read without another Claude call",
      e and "hikes" in e["notes"] and len(CALLS) == n_calls and SENT[-1][1] == "Saved under Emma.")
check("Emma is now active", store.kv_get("active") == e["id"])

# ---- a mentioned name switches context
reply(person="Sarah", replies=["x"])
post(bb("what should I say to sarah"))
check("a name in the text picks that person's thread", "ACTIVE PERSON: Sarah" in CALLS[-1][-1]["text"])

# ---- commands (no Claude calls)
n_calls = len(CALLS)
post(bb("list"))
check("list shows everyone", "Sarah" in SENT[0][1] and "Emma" in SENT[0][1])
post(bb("note emma: works at a gallery"))
check("note adds to her notes", "works at a gallery" in store.find("emma")["notes"])
post(bb("info emma"))
check("info shows the profile", "gallery" in SENT[0][1] and "hikes" in SENT[0][1])
post(bb("me: 34, Miami Beach, go-to is Broken Shaker"))
check("me: sets about-me used in the prompt", "Broken Shaker" in brain.about_me())
post(bb("forget emma"))
check("forget deletes her", store.find("emma") is None)
post(bb("help"))
check("help", "Commands" in SENT[0][1])
check("commands never call Claude", len(CALLS) == n_calls)

# ---- images Claude can't read
post(bb("", atts=["att-heic"]))
check("HEIC: says so, no Claude call", "can't read that image" in SENT[0][1] and len(CALLS) == n_calls)

# ---- duplicate deliveries
reply(person="Sarah", replies=["y"])
post(bb("sarah again", guid="dup"))
n_calls = len(CALLS)
post(bb("sarah again", guid="dup"))
check("a re-delivered message is handled once", not SENT and len(CALLS) == n_calls)

# ---- errors reach the phone
REPLIES.append("not json at all")
post(bb("sarah?"))
check("a bad model reply comes back as an error message", SENT and "error" in SENT[0][1].lower())

# ---- self-chat mode (Mac signed in to Jake's own Apple ID)
config.BB_SELF_CHAT_GUID = "iMessage;-;jake@icloud.com"
reply(person="Sarah", replies=["self-chat option"])
post(bb("sarah?", from_me=True, chat=config.BB_SELF_CHAT_GUID, sender=""))
check("self-chat: my own message in that chat is answered", SENT and SENT[-1][1] == "self-chat option")
n_calls = len(CALLS)
post(bb("self-chat option", from_me=True, chat=config.BB_SELF_CHAT_GUID, sender=""))
check("self-chat: the bot's own echo is ignored", not SENT and len(CALLS) == n_calls)
post(bb("sarah?", from_me=True, chat="iMessage;-;+13055550000", sender=""))
check("self-chat: my messages in other chats are ignored", not SENT and len(CALLS) == n_calls)
config.BB_SELF_CHAT_GUID = ""

# ---- a screenshot and the text sent right after it are one request
import time  # noqa: E402
config.DEBOUNCE_S = 0.3
reply(person="Sarah", replies=["combined"])
n_calls = len(CALLS)
post(bb("", atts=["att-png"]))
client.post("/webhook?token=tok", json=bb("she sent this an hour ago"))
time.sleep(1.0)
last = CALLS[-1]
check("debounce: one Claude call carrying both the image and the text",
      len(CALLS) == n_calls + 1 and last[0]["type"] == "image" and "an hour ago" in last[-1]["text"])
config.DEBOUNCE_S = 0

# ---- transports
sb = transport.Sendblue()
got = sb.parse({"content": "hey", "from_number": "+15550001111", "is_outbound": False,
                "media_url": "https://cdn/x.png", "message_handle": "h1", "number": "+15550001111"})
check("sendblue inbound parsed", len(got) == 1 and got[0].chat == "+15550001111"
      and got[0].attachments == ["https://cdn/x.png"])
check("sendblue outbound echo dropped", sb.parse({"content": "x", "from_number": "+1", "is_outbound": True}) == [])
check("bluebubbles ignores non-message events", transport.BlueBubbles().parse({"type": "typing-indicator"}) == [])
check("bluebubbles strips the attachment placeholder char",
      transport.BlueBubbles().parse(bb("￼hey"))[0].text == "hey")

# ---- health
h = client.get("/health").json()
check("health", h["ok"] and h["transport"] == "bluebubbles" and h["owner_set"] and h["key_set"])

print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILED: {FAILS}'}")
sys.exit(1 if FAILS else 0)
