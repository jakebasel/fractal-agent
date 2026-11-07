"""SQLite at DATA_DIR/wingman.db: the people Jake is talking to, what happened in each thread,
and a small key-value table. Screenshots are never stored, only what was read from them."""
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone

from . import config

_lock = threading.RLock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, key TEXT NOT NULL UNIQUE,
  stage TEXT DEFAULT '', summary TEXT DEFAULT '', notes TEXT DEFAULT '',
  created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL, kind TEXT NOT NULL,
  content TEXT NOT NULL, at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_person ON events(person_id, id);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(config.DATA_DIR / "wingman.db", check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(SCHEMA)
        return _conn


def _q(sql, args=()):
    with _lock:
        c = db().execute(sql, args)
        db().commit()
        return c


def key(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


# ---- kv ----
def kv_get(k, default=None):
    row = _q("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(row["v"]) if row else default


def kv_set(k, v):
    _q("INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v)))


# ---- people ----
def find(name: str):
    """Exact name, else a unique name starting with it ("sar" -> Sarah)."""
    k = key(name)
    if not k:
        return None
    row = _q("SELECT * FROM people WHERE key=?", (k,)).fetchone()
    if row:
        return dict(row)
    rows = _q("SELECT * FROM people WHERE key LIKE ? ORDER BY updated_at DESC",
              (k.replace("%", "") + "%",)).fetchall()
    return dict(rows[0]) if len(rows) == 1 else None


def get(pid: int):
    row = _q("SELECT * FROM people WHERE id=?", (pid,)).fetchone()
    return dict(row) if row else None


def create(name: str) -> dict:
    t = now_iso()
    _q("INSERT OR IGNORE INTO people(name, key, created_at, updated_at) VALUES(?,?,?,?)",
       (name.strip(), key(name), t, t))
    return dict(_q("SELECT * FROM people WHERE key=?", (key(name),)).fetchone())


def update(pid: int, **fields):
    fields = {k: v for k, v in fields.items() if k in ("name", "stage", "summary", "notes")}
    if "name" in fields:
        fields["key"] = key(fields["name"])
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    _q(f"UPDATE people SET {sets}, updated_at=? WHERE id=?", (*fields.values(), now_iso(), pid))


def add_notes(pid: int, notes: list):
    p = get(pid)
    have = [n for n in (p["notes"] or "").split("\n") if n.strip()]
    lower = {n.lower().lstrip("- ").strip() for n in have}
    for n in notes or []:
        n = str(n).strip().lstrip("- ").strip()
        if n and n.lower() not in lower:
            have.append("- " + n)
            lower.add(n.lower())
    update(pid, notes="\n".join(have[-40:]))


def people() -> list:
    return [dict(r) for r in _q("SELECT * FROM people ORDER BY updated_at DESC").fetchall()]


def forget(pid: int):
    _q("DELETE FROM events WHERE person_id=?", (pid,))
    _q("DELETE FROM people WHERE id=?", (pid,))
    if kv_get("active") == pid:
        kv_set("active", None)


# ---- events: jake (what he asked), convo (read from a screenshot or pasted), suggestion,
#      sent (what he actually sent), note ----
def add_event(pid: int, kind: str, content):
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    _q("INSERT INTO events(person_id, kind, content, at) VALUES(?,?,?,?)", (pid, kind, content, now_iso()))
    _q("UPDATE people SET updated_at=? WHERE id=?", (now_iso(), pid))


def events(pid: int, n: int = 20) -> list:
    rows = _q("SELECT * FROM events WHERE person_id=? ORDER BY id DESC LIMIT ?", (pid, n)).fetchall()
    return [dict(r) for r in reversed(rows)]


def last_suggestions(pid: int) -> list:
    row = _q("SELECT content FROM events WHERE person_id=? AND kind='suggestion' ORDER BY id DESC LIMIT 1",
             (pid,)).fetchone()
    if not row:
        return []
    try:
        return list(json.loads(row["content"]))
    except (ValueError, TypeError):
        return []
