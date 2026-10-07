"""SQLite on the /data volume. One row per fvg-mcp entry the agent reviewed.

Times are stored as UTC ISO strings and shown in ET (repo rule: humans see ET).
"""
import csv
import io
import json
import sqlite3
import threading
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
  entry_id        INTEGER PRIMARY KEY,   -- fvg-mcp entries.id
  symbol          TEXT,
  entry_at        TEXT,                  -- UTC ISO, when fvg-mcp recorded the entry
  reviewed_at     TEXT,                  -- UTC ISO
  session         TEXT,
  cascade         TEXT,
  direction       TEXT,
  mt_text         TEXT,
  mt_tf           TEXT,
  mt_cfg          TEXT,
  retrace         TEXT,
  entry           REAL,
  stop            REAL,
  target          REAL,
  decision        TEXT,                  -- TAKE | SKIP | MISSED | ERROR
  grade           TEXT,                  -- A+ | A | B | C
  size            TEXT,                  -- full | reduced | none
  confidence      REAL,
  hard_rule       TEXT,                  -- which hard rule fired, if any
  reasons         TEXT,                  -- JSON list
  boosters        TEXT,                  -- JSON list
  chart_read      TEXT,                  -- JSON from the vision model (null if no screenshot)
  screenshot      TEXT,                  -- file name used, if any
  screenshot_age_s REAL,
  context         TEXT,                  -- JSON snapshot sent to the decision model
  model_decision  TEXT,
  model_vision    TEXT,
  outcome         TEXT,                  -- fvg-mcp's scored outcome text
  r               REAL,                  -- fvg-mcp's scored R (as if taken, full size)
  paper_r         REAL,                  -- r * size multiplier if TAKE, else 0
  closed_at       TEXT,
  lesson          TEXT,                  -- JSON from the lessons step
  error           TEXT
);
CREATE TABLE IF NOT EXISTS lessons (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at  TEXT,
  entry_id    INTEGER,
  symbol      TEXT,
  verdict     TEXT,     -- right_take | wrong_take | right_skip | wrong_skip
  lesson      TEXT,
  rule_ref    TEXT,
  proposal    TEXT      -- suggested rule change, needs Jake's approval
);
CREATE TABLE IF NOT EXISTS screenshots (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TEXT,
  file        TEXT,
  bytes       INTEGER
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""

SIZE_MULT = {"full": 1.0, "reduced": 0.5, "none": 0.0}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_et(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return dt.astimezone(config.ET).strftime("%Y-%m-%d %H:%M:%S ET")


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DATA_DIR / "agent.db", check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


_conn = None


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = connect()
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def reset_for_tests():
    global _conn
    _conn = None


def kv_get(k, default=None):
    row = db().execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(row["v"]) if row else default


def kv_set(k, v):
    with _lock:
        db().execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)", (k, json.dumps(v)))
        db().commit()


def seen(entry_id: int) -> bool:
    return db().execute("SELECT 1 FROM decisions WHERE entry_id=?", (entry_id,)).fetchone() is not None


def insert_decision(row: dict):
    cols = list(row.keys())
    vals = [json.dumps(v) if isinstance(v, (list, dict)) else v for v in row.values()]
    with _lock:
        db().execute(
            f"INSERT OR REPLACE INTO decisions({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
            vals)
        db().commit()


def update_decision(entry_id: int, **fields):
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = [json.dumps(v) if isinstance(v, (list, dict)) else v for v in fields.values()]
    with _lock:
        db().execute(f"UPDATE decisions SET {sets} WHERE entry_id=?", (*vals, entry_id))
        db().commit()


def open_decisions():
    """Reviewed rows still waiting for fvg-mcp to score them."""
    return db().execute(
        "SELECT * FROM decisions WHERE r IS NULL AND decision IN ('TAKE','SKIP') "
        "ORDER BY entry_id").fetchall()


def add_lesson(entry_id, symbol, verdict, lesson, rule_ref, proposal):
    with _lock:
        db().execute(
            "INSERT INTO lessons(created_at,entry_id,symbol,verdict,lesson,rule_ref,proposal) "
            "VALUES(?,?,?,?,?,?,?)",
            (now_utc(), entry_id, symbol, verdict, lesson, rule_ref, proposal))
        db().commit()


def recent_lessons(n: int):
    return db().execute("SELECT * FROM lessons ORDER BY id DESC LIMIT ?", (n,)).fetchall()


def add_screenshot(file: str, nbytes: int):
    with _lock:
        db().execute("INSERT INTO screenshots(received_at,file,bytes) VALUES(?,?,?)",
                     (now_utc(), file, nbytes))
        db().commit()


def latest_screenshot():
    return db().execute("SELECT * FROM screenshots ORDER BY id DESC LIMIT 1").fetchone()


# ---- reporting -----------------------------------------------------------------------------

CSV_COLS = ["entry_id", "symbol", "entry_at_et", "session", "cascade", "direction", "mt_text",
            "mt_tf", "mt_cfg", "retrace", "entry", "stop", "target", "decision", "grade", "size",
            "confidence", "hard_rule", "reasons", "outcome", "r", "paper_r", "closed_at_et",
            "lesson", "screenshot_age_s"]


def decisions(limit=500, symbol=None, since_iso=None):
    q, args = "SELECT * FROM decisions", []
    where = []
    if symbol:
        where.append("symbol=?"); args.append(symbol)
    if since_iso:
        where.append("entry_at>=?"); args.append(since_iso)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY entry_id DESC LIMIT ?"
    args.append(limit)
    return db().execute(q, args).fetchall()


def _lesson_text(raw):
    if not raw:
        return ""
    try:
        return json.loads(raw).get("lesson", "")
    except (ValueError, AttributeError):
        return raw


def export_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for r in reversed(decisions(limit=100000)):
        reasons = r["reasons"]
        try:
            reasons = " | ".join(json.loads(reasons or "[]"))
        except ValueError:
            pass
        w.writerow([r["entry_id"], r["symbol"], to_et(r["entry_at"]), r["session"], r["cascade"],
                    r["direction"], r["mt_text"], r["mt_tf"], r["mt_cfg"], r["retrace"], r["entry"],
                    r["stop"], r["target"], r["decision"], r["grade"], r["size"], r["confidence"],
                    r["hard_rule"], reasons, r["outcome"], r["r"], r["paper_r"],
                    to_et(r["closed_at"]), _lesson_text(r["lesson"]), r["screenshot_age_s"]])
    return buf.getvalue()


def write_csv_file():
    path = config.DATA_DIR / "trades.csv"
    path.write_text(export_csv())
    return path


def stats(since_iso=None):
    """Paper results: how the AI's TAKEs did vs what it SKIPPED (the filter's edge)."""
    rows = [r for r in decisions(limit=100000, since_iso=since_iso) if r["r"] is not None]

    def summ(rs, key="r"):
        vals = [x[key] for x in rs if x[key] is not None]
        n = len(vals)
        if not n:
            return {"n": 0}
        wins = sum(1 for v in vals if v > 0)
        cum, peak, dd = 0.0, 0.0, 0.0
        for v in vals:
            cum += v
            peak = max(peak, cum)
            dd = min(dd, cum - peak)
        return {"n": n, "win_pct": round(100 * wins / n, 1), "avg_r": round(sum(vals) / n, 3),
                "total_r": round(sum(vals), 2), "max_dd_r": round(dd, 2)}

    rows.sort(key=lambda x: x["entry_id"])
    takes = [r for r in rows if r["decision"] == "TAKE"]
    skips = [r for r in rows if r["decision"] == "SKIP"]
    return {
        "paper_book": summ(takes, "paper_r"),
        "taken_as_full_size": summ(takes),
        "skipped_counterfactual": summ(skips),
        "all_engine_entries": summ(rows),
        "note": "r = fvg-mcp's scored result as if taken at full size; paper_r applies the "
                "agent's size (reduced = 0.5). The filter adds value if taken avg_r > all avg_r.",
    }
