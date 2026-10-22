"""The reference library (2026-10-20): one searchable store of everything discussed.

Holds the course material in knowledge/, every live-session transcript (pushed by the Zoom
tool on the Mac Mini Hub to POST /library/ingest, plus the backlog), each session's digest,
and the agents' own memory (trade lessons, Hermes reviews). Lives in agent.db on the /data
volume, so it survives redeploys (repo files reset to git; this does not).

Search is SQLite FTS5 (bm25), milliseconds over the whole library. Jake asks through Jake
Trade Help or Claude (knowledge_search, session_digests); the decider and Hermes search the
same thing, so a new session shapes the next decision. A new transcript also gets a digest
(LIBRARY_DIGEST_MODEL, Sonnet by default) whose candidate rules are filed as hypotheses --
they still need Jake's Approve, like any other proposal.
"""
import hashlib
import json
import logging
import re
import threading
import time

from . import config, store

log = logging.getLogger("library")
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS library_docs (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  kind      TEXT,     -- course | live_session | digest | lesson | review
  source    TEXT UNIQUE,
  title     TEXT,
  at        TEXT,     -- when it was said / written (UTC ISO or a date)
  hash      TEXT,
  text      TEXT,
  digest    TEXT,     -- JSON, live sessions only
  added_at  TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS library_fts USING fts5(
  body, title, kind UNINDEXED, source UNINDEXED, at UNINDEXED, doc_id UNINDEXED,
  tokenize = 'porter unicode61'
);
"""
_ready = threading.local()


def _db():
    c = store.db()
    if not getattr(_ready, "ok", False):
        with _lock:
            c.executescript(SCHEMA)
            c.commit()
        _ready.ok = True
    return c


def _chunks(text: str):
    from .knowledge import _chunks as kc
    return [c for c in kc(text) if len(c) > 80]


def add_document(kind: str, source: str, title: str, at: str, text: str) -> tuple[int, bool]:
    """Insert or replace one document and its search chunks. -> (doc_id, changed)."""
    text = (text or "").strip()
    h = hashlib.sha1(text.encode()).hexdigest()
    c = _db()
    with _lock:
        row = c.execute("SELECT id, hash FROM library_docs WHERE source=?", (source,)).fetchone()
        if row and row["hash"] == h:
            return row["id"], False
        if row:
            doc_id = row["id"]
            c.execute("UPDATE library_docs SET kind=?, title=?, at=?, hash=?, text=? WHERE id=?",
                      (kind, title, at, h, text, doc_id))
            c.execute("DELETE FROM library_fts WHERE doc_id=?", (doc_id,))
        else:
            doc_id = c.execute(
                "INSERT INTO library_docs(kind, source, title, at, hash, text, added_at) "
                "VALUES(?,?,?,?,?,?,?)", (kind, source, title, at, h, text, store.now_utc())).lastrowid
        c.executemany("INSERT INTO library_fts(body, title, kind, source, at, doc_id) VALUES(?,?,?,?,?,?)",
                      [(ch, title, kind, source, at, doc_id) for ch in _chunks(text)])
        c.commit()
    return doc_id, True


_WORD = re.compile(r"[A-Za-z0-9]+")


def _fts_query(query: str) -> str:
    """Free text -> an FTS5 OR query (quoted terms, so punctuation can't break the syntax),
    with the same trading-shorthand expansion the course search uses (DB -> double break...)."""
    from .knowledge import _EXPAND, _STOP
    words = [w for w in _WORD.findall(query.lower()) if w not in _STOP or w in _EXPAND]
    extra = []
    for w in words:
        if w in _EXPAND:
            extra += _WORD.findall(_EXPAND[w])
    terms = list(dict.fromkeys(words + extra))[:40]
    return " OR ".join(f'"{t}"' for t in terms)


def search(query: str, k: int = 6, kind: str | None = None, since: str | None = None,
           kinds: tuple | None = None) -> list[dict]:
    q = _fts_query(query or "")
    if not q:
        return []
    sql = ("SELECT body, title, kind, source, at, bm25(library_fts, 1.0, 0.3) AS s FROM library_fts "
           "WHERE library_fts MATCH ?")
    args = [q]
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    if kinds:
        sql += " AND kind IN (" + ",".join("?" * len(kinds)) + ")"
        args += list(kinds)
    if since:
        sql += " AND at >= ?"
        args.append(since)
    sql += " ORDER BY s LIMIT ?"
    args.append(max(k * 4, 20))
    out, per_doc = [], {}
    for r in _db().execute(sql, args).fetchall():
        if per_doc.get(r["source"], 0) >= 2:      # spread results across documents
            continue
        per_doc[r["source"]] = per_doc.get(r["source"], 0) + 1
        out.append({"source": r["source"], "title": r["title"], "kind": r["kind"], "at": r["at"],
                    "score": round(-r["s"], 2), "text": r["body"]})
        if len(out) >= k:
            break
    return out


def count() -> dict:
    rows = _db().execute("SELECT kind, COUNT(*) n FROM library_docs GROUP BY kind").fetchall()
    return {r["kind"]: r["n"] for r in rows}


# ---- keeping it current ---------------------------------------------------------------------

def sync_internal() -> int:
    """Course files from the repo (re-indexed when they change) and every new lesson / review."""
    from .knowledge import KNOWLEDGE_DIR
    n = 0
    for p in sorted(KNOWLEDGE_DIR.rglob("*.txt")) + sorted(KNOWLEDGE_DIR.rglob("*.md")):
        rel = str(p.relative_to(KNOWLEDGE_DIR))
        kind = "live_session" if "live" in rel.lower() else "course"
        n += add_document(kind, "repo:" + rel, p.stem, "", p.read_text(errors="ignore"))[1]
    c = _db()
    last = int(store.kv_get("library_last_lesson") or 0)
    for r in c.execute("SELECT * FROM lessons WHERE id > ? ORDER BY id", (last,)).fetchall():
        body = f"{r['symbol']} {r['verdict']}: {r['lesson']}"
        n += add_document("lesson", f"lesson:{r['id']}", f"Lesson #{r['id']} {r['symbol'] or ''}",
                          r["created_at"] or "", body)[1]
        store.kv_set("library_last_lesson", r["id"])
    last = int(store.kv_get("library_last_review") or 0)
    for r in c.execute("SELECT * FROM reviews WHERE id > ? ORDER BY id", (last,)).fetchall():
        body = " ".join(str(r[k] or "") for k in ("verdict", "summary", "exit_notes"))
        n += add_document("review", f"review:{r['id']}", f"{r['reviewer']} review #{r['id']}",
                          r["at"] or "", body)[1]
        store.kv_set("library_last_review", r["id"])
    return n


_last_sync = {"t": 0.0}


def sync_if_due(every_s: int = 300) -> int:
    if time.time() - _last_sync["t"] < every_s:
        return 0
    _last_sync["t"] = time.time()
    try:
        return sync_internal()
    except Exception as e:
        log.warning("library sync failed: %s", e)
        return 0


_last_tx = {"t": 0.0}


def sync_transcripts(fvg) -> int:
    """fvg-mcp's /transcripts page (Postgres table, the SOURCE OF TRUTH for the rules) into the
    library, via its read-only `transcripts` tool (2026-10-22). Incremental on added_at."""
    since = store.kv_get("library_tx_since") or None
    try:
        listing = fvg.transcripts(since=since, limit=50)
    except Exception as e:
        log.warning("fvg-mcp transcripts: %s", e)
        return 0
    rows = sorted((listing or {}).get("transcripts") or [], key=lambda r: (r.get("added_at") or "", r.get("id") or 0))
    n = 0
    for r in rows:
        try:
            full = fvg.transcripts(id=r["id"])
        except Exception as e:
            log.warning("fvg-mcp transcript %s: %s", r.get("id"), e)
            break
        text = (full or {}).get("content") or ""
        if len(text.strip()) < 200:
            store.kv_set("library_tx_since", r.get("added_at") or since)
            continue
        kind = "course" if str(r.get("kind") or "").lower().startswith("course") else "live_session"
        title = f"{r.get('name')} ({r.get('date_label')})" if r.get("date_label") else str(r.get("name"))
        n += add_document(kind, f"fvg-mcp:transcript:{r['id']}", title, r.get("date_label") or r.get("added_at") or "", text)[1]
        store.kv_set("library_tx_since", r.get("added_at") or since)
    if n:
        log.info("library: %d transcript(s) from fvg-mcp", n)
    return n


def sync_transcripts_if_due(fvg, every_s: int | None = None) -> int:
    every_s = every_s if every_s is not None else config.TRANSCRIPTS_SYNC_S
    if every_s <= 0 or time.time() - _last_tx["t"] < every_s:
        return 0
    _last_tx["t"] = time.time()
    try:
        return sync_transcripts(fvg)
    except Exception as e:
        log.warning("transcripts sync failed: %s", e)
        return 0


# ---- live sessions ---------------------------------------------------------------------------

DIGEST_SYSTEM = """You digest one live trading-session transcript for a Fractal Effects
(Market Translator) trader's reference library. The transcript is the instructor and a
moderator only; everyone else was muted. Lines start with [HH:MM:SS] ET timestamps.

Return ONE JSON object:
{"title": "<5-10 words>",
 "summary": "<4-8 sentences: what was taught and traded>",
 "topics": ["<short topic>", ...],
 "trade_calls": [{"time": "HH:MM", "instrument": "<NAS|US500|US30|gold|...>", "side": "long|short",
                  "what": "<entry/stop/target or the call in his words>", "outcome": "<if said>"}],
 "teachings": [{"time": "HH:MM", "point": "<a rule, nuance or correction he stated>"}],
 "rule_proposals": [{"title": "<short>", "rule": "IF <condition> THEN <TAKE/SKIP/size/stop>",
                     "quote": "<his words>", "time": "HH:MM"}]}
Report only what he actually said. rule_proposals: at most 3, only clear, testable rules that
are NOT already in the rulebook below; empty list if none.

RULEBOOK (for what is already known):
"""


def _rulebook() -> str:
    from . import prompts
    return (prompts._read("amendments.md") + "\n" + prompts._read("live_rules.md"))[:30000]


def digest(doc_id: int) -> dict:
    from . import llm
    row = _db().execute("SELECT * FROM library_docs WHERE id=?", (doc_id,)).fetchone()
    text = row["text"][:400_000]
    messages = [{"role": "system", "content": DIGEST_SYSTEM + _rulebook()},
                {"role": "user", "content": f"Session: {row['title']} ({row['at']})\n\n{text}"}]
    d = llm.parse_json(llm._post(config.LIBRARY_DIGEST_MODEL, messages, max_tokens=12000,
                                 purpose="library_digest"))
    with _lock:
        _db().execute("UPDATE library_docs SET digest=? WHERE id=?", (json.dumps(d), doc_id))
        _db().commit()
    body = "\n".join([d.get("summary") or "", "Topics: " + ", ".join(d.get("topics") or [])] +
                     [f"[{x.get('time')}] {x.get('point')}" for x in d.get("teachings") or []] +
                     [f"[{x.get('time')}] CALL {x.get('instrument')} {x.get('side')}: {x.get('what')} "
                      f"{x.get('outcome') or ''}" for x in d.get("trade_calls") or []])
    add_document("digest", f"digest:{row['source']}", d.get("title") or row["title"], row["at"], body)
    from . import learning
    for p in (d.get("rule_proposals") or [])[:3]:
        learning.register_proposal({"proposal": p.get("rule"), "proposal_title": p.get("title"),
                                    "rule_ref": f"live session {row['at']} {p.get('time') or ''}".strip()},
                                   0, source="live-session",
                                   note=f"\"{(p.get('quote') or '')[:300]}\" ({row['title']})")
    return d


def digest_text(title: str, d: dict) -> str:
    """The digest as a Telegram message."""
    lines = [f"📚 {d.get('title') or title}", "", d.get("summary") or ""]
    if d.get("trade_calls"):
        lines += ["", "Calls:"] + [f"• {x.get('time')} {x.get('instrument')} {x.get('side')}: {x.get('what')}"
                                   + (f" → {x.get('outcome')}" if x.get("outcome") else "") for x in d["trade_calls"]]
    if d.get("teachings"):
        lines += ["", "Teachings:"] + [f"• {x.get('time')} {x.get('point')}" for x in d["teachings"][:8]]
    if d.get("rule_proposals"):
        lines += ["", "Filed as rule proposals (need your Approve on the dashboard):"] + \
                 [f"• {p.get('title')}: {p.get('rule')}" for p in d["rule_proposals"][:3]]
    return "\n".join(lines)


def ingest_session(source: str, title: str, at: str, text: str, run_digest: bool = True,
                   notify: bool = False) -> dict:
    doc_id, changed = add_document("live_session", source, title, at, text)
    out = {"doc_id": doc_id, "changed": changed, "digest": None}
    if run_digest and changed:
        try:
            out["digest"] = digest(doc_id)
        except Exception as e:
            log.exception("digest failed for %s", source)
            out["digest_error"] = f"{type(e).__name__}: {e}"[:300]
    if notify and config.TELEGRAM_PUSH and out["digest"] and config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        try:
            from . import telegram_bot
            telegram_bot.send(config.TELEGRAM_CHAT_ID, digest_text(title, out["digest"]))
        except Exception as e:
            log.warning("digest message failed: %s", e)
    return out


def session_digests(days: float = 30, limit: int = 20) -> list[dict]:
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=float(days))).strftime("%Y-%m-%d")
    rows = _db().execute(
        "SELECT title, at, source, digest FROM library_docs WHERE kind='live_session' "
        "AND digest IS NOT NULL AND at >= ? ORDER BY at DESC LIMIT ?", (since, limit)).fetchall()
    return [{"title": r["title"], "at": r["at"], "source": r["source"], **json.loads(r["digest"])}
            for r in rows]
