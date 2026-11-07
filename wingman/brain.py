"""One Claude call per request: Jake's message (text and/or screenshots) plus what we know about
the person -> a read on where things stand and the next texts to send, as JSON."""
import base64
import json
import re
import time
from datetime import datetime

import httpx

from . import config, store


class LLMError(RuntimeError):
    pass


SYSTEM = """You are Jake's texting wingman. He sends you a woman's name, notes about her, or
screenshots of a conversation (iMessage, Hinge, Tinder, Bumble, Raya, Instagram DMs). You read
where things stand and write his next text, steering toward a concrete in-person plan: drinks or
dinner, with a day and a place.

How to read a screenshot:
- iMessage: Jake's bubbles are on the RIGHT (blue/green), hers on the LEFT (grey). Dating apps
  and Instagram: his are on the right too. Her name is usually in the header.
- Transcribe only the most recent messages (up to ~25), oldest first, and only ones not already
  in the logged thread below. Note timestamps / "Read" / "Delivered" if visible -- gaps matter.
- If the screenshot is a dating profile rather than a chat, pull out prompts, photos' context,
  job, school, interests, and write an opener that references something specific.

Reading interest (say it plainly, one or two lines):
- Warm: she asks questions back, writes as much as he does, quick replies, jokes, emojis, uses
  his name, suggests things herself.
- Lukewarm: answers but doesn't ask, short replies, slow.
- Cold: one-word answers, long gaps, dodged a plan twice, or said no / has a boyfriend.

Moving it forward:
- The goal of the thread is a date, not a pen pal. Once there's a bit of rapport (a few good
  back-and-forths, she's warm), ask -- don't wait for a perfect moment. If she's already warm and
  it's been more than ~a day of texting, the ask should be one of the options.
- A good ask is specific and easy to say yes to: one idea, a day or two, a place type or a named
  spot if Jake's info has one ("drinks at <spot> thursday?"), not "we should hang sometime".
- If she said yes to a plan, help lock in logistics (day, time, place) and confirm the day of.
- If she's lukewarm: one light, interesting message that gives her something easy to reply to.
- If she's cold or said no: say so, suggest at most one low-key message or letting it go. Never
  write pressure, guilt-tripping, negging, or anything after a clear no.

How the texts should sound:
- Like Jake texting, not a pickup artist: short, natural, lowercase is fine, match her length and
  energy, at most one question per text. Reference specifics she said or her profile shows.
- Playful > clever. No cheesy lines, no "m'lady", no essays, no excessive emojis.
- Never invent facts about Jake: use only what ABOUT JAKE says. If an option needs a detail you
  don't have (his neighborhood, a favorite bar), keep it generic or put a [placeholder].
- Give three options with different tones (e.g. playful / sincere / direct). If it's time to ask,
  put the ask in "ask" as well.

Jake may also ask a plain question ("how long should I wait", "she left me on read, now what",
"make #2 funnier", "she said yes, what now"); answer it in "message" and still give options when
useful. "Make #2 funnier" refers to the last suggestions in the logged thread.

Which person: if the message or screenshot names her, use that name exactly as shown (first name,
plus an initial or the app if Jake gives one). If it's clearly a follow-up about the ACTIVE
person, use her name. If you can't tell who it is, set person to null.

Reply with ONE JSON object and nothing else:
{
  "person": "Sarah" or null,
  "transcript": [{"from": "her" | "jake", "text": "...", "when": "optional"}],
  "stage": "opener" | "rapport" | "flirting" | "ready_to_ask" | "asked" | "date_set" | "after_date" | "cold",
  "read": "one or two short lines: interest level and why",
  "replies": ["option 1", "option 2", "option 3"],
  "ask": "the date ask, or empty if it's too early",
  "tip": "optional one-line timing/strategy tip (e.g. wait an hour, she's been slow)",
  "notes_add": ["new facts about her worth remembering: job, interests, plans, inside jokes"],
  "summary": "one line: where things stand now",
  "message": "a direct answer if Jake asked a question, else empty"
}
Plain text inside the strings: no markdown, no asterisks."""


def about_me() -> str:
    return store.kv_get("about_me") or config.ABOUT_ME or "(nothing yet -- Jake can set it with `me: ...`)"


def _fmt_event(e: dict) -> str:
    try:
        when = datetime.fromisoformat(e["at"]).astimezone(config.ET).strftime("%a %b %d %I:%M %p ET")
    except ValueError:
        when = e["at"]
    c = e["content"]
    if e["kind"] == "convo":
        try:
            lines = json.loads(c)
            c = "\n".join(f"  {m.get('from', '?')}: {m.get('text', '')}" for m in lines)
        except (ValueError, TypeError, AttributeError):
            pass
        return f"[{when}] conversation read:\n{c}"
    if e["kind"] == "suggestion":
        try:
            c = " | ".join(f"#{i + 1} {s}" for i, s in enumerate(json.loads(c)))
        except (ValueError, TypeError):
            pass
        return f"[{when}] you suggested: {c}"
    label = {"jake": "Jake asked", "sent": "Jake SENT", "note": "Jake's note"}.get(e["kind"], e["kind"])
    return f"[{when}] {label}: {c}"


def person_block(p: dict | None) -> str:
    if not p:
        return "ACTIVE PERSON: none"
    ev = store.events(p["id"], config.HISTORY_EVENTS)
    return (f"ACTIVE PERSON: {p['name']}\nstage: {p['stage'] or '?'}\nsummary: {p['summary'] or '-'}\n"
            f"notes:\n{p['notes'] or '-'}\nlogged thread (oldest first):\n"
            + ("\n".join(_fmt_event(e) for e in ev) or "(nothing logged yet)"))


def roster_block() -> str:
    ps = store.people()[:30]
    if not ps:
        return "OTHER PEOPLE: none yet"
    return "OTHER PEOPLE (name - stage - summary):\n" + "\n".join(
        f"- {p['name']} - {p['stage'] or '?'} - {p['summary'] or ''}" for p in ps)


def build_user_content(text: str, images: list, person: dict | None) -> list:
    now = datetime.now(config.ET).strftime("%A %b %d %Y, %I:%M %p ET")
    ctx = (f"NOW: {now}\n\nABOUT JAKE:\n{about_me()}\n\n{roster_block()}\n\n{person_block(person)}\n\n"
           f"JAKE'S MESSAGE{' (with %d screenshot%s)' % (len(images), 's' if len(images) > 1 else '') if images else ''}:\n"
           f"{text or '(no text: read the screenshot and suggest my next text)'}")
    content = []
    for b in images:
        content.append({"type": "image", "source": {"type": "base64", "media_type": mime(b),
                                                    "data": base64.b64encode(b).decode()}})
    content.append({"type": "text", "text": ctx})
    return content


def mime(b: bytes) -> str:
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return ""   # HEIC and anything else Claude can't read


def call_claude(system: str, content: list) -> str:
    if not config.ANTHROPIC_API_KEY:
        raise LLMError("ANTHROPIC_API_KEY is not set")
    # no temperature / prefill / thinking fields: Claude 5.5 models reject them; effort sets depth
    body = {"model": config.MODEL, "max_tokens": config.MAX_TOKENS,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
            "output_config": {"effort": config.EFFORT}}
    headers = {"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": config.ANTHROPIC_VERSION,
               "content-type": "application/json"}
    t0 = time.time()
    try:
        r = httpx.post(config.ANTHROPIC_URL, json=body, headers=headers, timeout=config.LLM_TIMEOUT_S)
    except httpx.HTTPError as e:
        raise LLMError(f"{config.MODEL}: {e}") from e
    if r.status_code >= 400:
        raise LLMError(f"{config.MODEL}: HTTP {r.status_code} {r.text[:300]}")
    data = r.json()
    text = "".join(b.get("text") or "" for b in data.get("content") or [] if b.get("type") == "text")
    if not text.strip():
        raise LLMError(f"empty reply (stop_reason={data.get('stop_reason')}, {int(time.time() - t0)}s)")
    return text


def parse_json(text: str) -> dict:
    """First JSON object in the reply; tolerates ```json fences and prose around it."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else text
    dec = json.JSONDecoder()
    pos = raw.find("{")
    while pos >= 0:
        try:
            obj, _ = dec.raw_decode(raw, pos)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        pos = raw.find("{", pos + 1)
    raise LLMError(f"no JSON in reply: {text[:200]}")


def think(text: str, images: list, person: dict | None) -> dict:
    out = parse_json(call_claude(SYSTEM, build_user_content(text, images, person)))
    out["replies"] = [str(r).strip() for r in (out.get("replies") or []) if str(r).strip()][:4]
    for k in ("read", "ask", "tip", "summary", "message", "stage"):
        out[k] = str(out.get(k) or "").strip()
    out["transcript"] = [m for m in (out.get("transcript") or []) if isinstance(m, dict) and m.get("text")]
    out["notes_add"] = [str(n) for n in (out.get("notes_add") or []) if str(n).strip()]
    p = out.get("person")
    out["person"] = str(p).strip() if p and str(p).strip().lower() not in ("null", "none", "unknown") else None
    return out
