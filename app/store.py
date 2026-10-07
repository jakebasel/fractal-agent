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

_lock = threading.RLock()   # re-entrant: a write may trigger first-time connection setup

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
CREATE TABLE IF NOT EXISTS api_calls (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  at          TEXT,
  purpose     TEXT,     -- vision | decision | lesson | hypothesis | shadow | jev
  model       TEXT,
  in_tokens   INTEGER,
  out_tokens  INTEGER,
  cost        REAL,     -- USD as reported by OpenRouter
  ms          INTEGER,
  ok          INTEGER,
  error       TEXT
);
CREATE TABLE IF NOT EXISTS rule_versions (
  version     TEXT PRIMARY KEY,   -- short hash of rules/*.md
  first_seen  TEXT,
  amendments  TEXT                -- amendments.md at the time, for the history view
);
CREATE TABLE IF NOT EXISTS hypotheses (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at  TEXT,
  title       TEXT,     -- short name
  rule        TEXT,     -- the proposed change, phrased as a rule
  rule_ref    TEXT,
  source      TEXT,     -- lesson | engine-data | jake
  status      TEXT,     -- testing | queued | approved | rejected | retired
  support     INTEGER DEFAULT 1,   -- how many lessons proposed it
  entry_ids   TEXT,     -- JSON list of the trades that suggested it
  decided_at  TEXT,
  note        TEXT
);
CREATE TABLE IF NOT EXISTS scans (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  at          TEXT,
  files       TEXT,
  symbol      TEXT,
  play        TEXT,
  direction   TEXT,
  stage       TEXT,     -- forming | ready | entered
  entry       REAL, stop REAL, target REAL,
  confidence  REAL,
  reasons     TEXT,     -- JSON
  engine_has_it INTEGER
);
CREATE TABLE IF NOT EXISTS shadow (
  entry_id    INTEGER,
  hyp_id      INTEGER,
  decision    TEXT,     -- what the agent would have done with this change in the rules
  size        TEXT,
  changed     INTEGER,  -- 1 if different from the real decision
  why         TEXT,
  at          TEXT,
  PRIMARY KEY (entry_id, hyp_id)
);
"""

# columns added after v1; ALTERed into an existing database at start-up
MIGRATIONS = {
    "decisions": {"play": "TEXT", "rules_version": "TEXT", "jev": "TEXT", "jev_p_take": "REAL",
                  "path": "TEXT", "news": "TEXT", "vision_score": "REAL", "vision_note": "TEXT",
                  "kill_events": "TEXT", "managed_r": "REAL", "managed_outcome": "TEXT",
                  "managed_paper_r": "REAL", "managed_tries": "INTEGER", "shadow_tries": "INTEGER"},
    "screenshots": {"batch": "TEXT", "part": "INTEGER", "kind": "TEXT"},
    "scans": {"r": "REAL", "outcome": "TEXT", "scored_at": "TEXT", "score_tries": "INTEGER"},
}

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


_local = threading.local()


def db() -> sqlite3.Connection:
    """One connection per thread (agent loop, HTTP). WAL lets readers and the writer run side
    by side; a shared connection would let a commit on one thread truncate a read on another."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = connect()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        with _lock:
            conn.executescript(SCHEMA)
            for table, cols in MIGRATIONS.items():
                have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                for col, typ in cols.items():
                    if col not in have:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            conn.commit()
        _local.conn = conn
    return conn


def reset_for_tests():
    _local.conn = None


def kv_get(k, default=None):
    row = db().execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(row["v"]) if row else default


def kv_set(k, v):
    with _lock:
        db().execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)", (k, json.dumps(v)))
        db().commit()


def seen(entry_id: int) -> bool:
    return db().execute("SELECT 1 FROM decisions WHERE entry_id=?", (entry_id,)).fetchone() is not None


def retryable_error(entry_id: int, max_age_s: int) -> bool:
    """An ERROR row for an entry that is still fresh gets another go (transient model failure)."""
    row = db().execute("SELECT decision, entry_at FROM decisions WHERE entry_id=?", (entry_id,)).fetchone()
    if not row or row["decision"] != "ERROR" or not row["entry_at"]:
        return False
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["entry_at"].replace("Z", "+00:00"))).total_seconds()
    return age <= max_age_s


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


def managed_todo(limit=3, max_tries=4):
    """Settled rows (older than 2.5h) still without a management-rules score."""
    cutoff = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 2.5 * 3600,
                                    tz=timezone.utc).isoformat()
    return db().execute(
        "SELECT * FROM decisions WHERE r IS NOT NULL AND managed_r IS NULL AND decision IN ('TAKE','SKIP') "
        "AND entry_at<=? AND COALESCE(managed_tries,0)<? ORDER BY entry_id DESC LIMIT ?",
        (cutoff, max_tries, limit)).fetchall()


def managed_try(entry_id):
    with _lock:
        db().execute("UPDATE decisions SET managed_tries=COALESCE(managed_tries,0)+1 WHERE entry_id=?", (entry_id,))
        db().commit()


def open_decisions():
    """Reviewed rows still waiting for fvg-mcp to score them."""
    # ERROR / MISSED rows are settled too (paper_r = 0) so the core book stays complete
    return db().execute(
        "SELECT * FROM decisions WHERE r IS NULL AND decision IN ('TAKE','SKIP','ERROR','MISSED') "
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


def add_screenshot(file: str, nbytes: int, batch: str | None = None, part: int | None = None,
                   kind: str | None = None):
    with _lock:
        db().execute("INSERT INTO screenshots(received_at,file,bytes,batch,part,kind) VALUES(?,?,?,?,?,?)",
                     (now_utc(), file, nbytes, batch, part, kind))
        db().commit()


def add_scan(at, files, symbol, play, direction, stage, entry, stop, target, confidence, reasons, engine_has_it):
    with _lock:
        db().execute("INSERT INTO scans(at,files,symbol,play,direction,stage,entry,stop,target,confidence,reasons,engine_has_it) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (at, files, symbol, play, direction, stage, entry, stop, target, confidence,
                      json.dumps(reasons or []), 1 if engine_has_it else 0))
        db().commit()


def scans(limit=50):
    return db().execute("SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def scans_to_score(older_than_iso, max_tries=4):
    return db().execute(
        "SELECT * FROM scans WHERE stage='ready' AND entry IS NOT NULL AND stop IS NOT NULL "
        "AND target IS NOT NULL AND r IS NULL AND at<=? AND COALESCE(score_tries,0)<? ORDER BY id",
        (older_than_iso, max_tries)).fetchall()


def score_scan(scan_id, r, outcome):
    with _lock:
        db().execute("UPDATE scans SET r=?, outcome=?, scored_at=?, score_tries=COALESCE(score_tries,0)+1 WHERE id=?",
                     (r, outcome, now_utc(), scan_id))
        db().commit()


def scan_try(scan_id):
    with _lock:
        db().execute("UPDATE scans SET score_tries=COALESCE(score_tries,0)+1 WHERE id=?", (scan_id,))
        db().commit()


def scored_scans():
    return db().execute("SELECT * FROM scans WHERE r IS NOT NULL ORDER BY id").fetchall()


def latest_screenshot():
    return db().execute("SELECT * FROM screenshots ORDER BY id DESC LIMIT 1").fetchone()


def latest_screenshot_set(settle_s: float = 6.0):
    """The newest screenshot plus the other windows captured in the same batch, left first.
    A batch's parts arrive a second or two apart; a batch younger than `settle_s` may still be
    incomplete, so the previous one is used instead."""
    last = latest_screenshot()
    if not last or not last["batch"]:
        return [last] if last else []
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(last["received_at"])).total_seconds()
    if age < settle_s:
        prev = db().execute("SELECT * FROM screenshots WHERE batch IS NOT NULL AND batch!=? ORDER BY id DESC LIMIT 1",
                            (last["batch"],)).fetchone()
        if prev:
            last = prev
    return db().execute("SELECT * FROM screenshots WHERE batch=? ORDER BY part",
                        (last["batch"],)).fetchall()


# ---- spend -----------------------------------------------------------------------------------

def log_api_call(purpose, model, in_tok, out_tok, cost, ms, ok, error=None):
    with _lock:
        db().execute("INSERT INTO api_calls(at,purpose,model,in_tokens,out_tokens,cost,ms,ok,error) "
                      "VALUES(?,?,?,?,?,?,?,?,?)",
                      (now_utc(), purpose, model, in_tok, out_tok, cost, ms, 1 if ok else 0, error))
        db().commit()


def spend(since_iso=None) -> dict:
    where, args = "", []
    if since_iso:
        where, args = "WHERE at>=?", [since_iso]
    rows = db().execute(
        f"SELECT purpose, model, COUNT(*) n, SUM(COALESCE(cost,0)) cost, AVG(ms) ms, "
        f"SUM(1-ok) errors FROM api_calls {where} GROUP BY purpose, model ORDER BY cost DESC",
        args).fetchall()
    out = [{"purpose": r["purpose"], "model": r["model"], "calls": r["n"],
            "cost_usd": round(r["cost"] or 0, 6), "avg_ms": int(r["ms"] or 0),
            "errors": r["errors"]} for r in rows]
    return {"total_usd": round(sum(x["cost_usd"] for x in out), 6),
            "calls": sum(x["calls"] for x in out), "by_purpose": out}


def spend_today() -> float:
    since = datetime.now(config.ET).replace(hour=0, minute=0, second=0, microsecond=0) \
        .astimezone(timezone.utc).isoformat()
    row = db().execute("SELECT SUM(COALESCE(cost,0)) c FROM api_calls WHERE at>=?", (since,)).fetchone()
    return float(row["c"] or 0)


def over_budget() -> bool:
    """True when today's spend passed DAILY_BUDGET_USD: optional calls pause, decisions continue."""
    return config.DAILY_BUDGET_USD > 0 and spend_today() >= config.DAILY_BUDGET_USD


def spend_by_day(days=30):
    since = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - days * 86400,
                                   tz=timezone.utc).isoformat()
    rows = db().execute("SELECT at, cost FROM api_calls WHERE at>=?", (since,)).fetchall()
    by = {}
    for r in rows:
        d = to_et(r["at"])[:10]
        by[d] = by.get(d, 0.0) + (r["cost"] or 0)
    return [{"day": d, "cost_usd": round(v, 4)} for d, v in sorted(by.items())]


# ---- rule versions ---------------------------------------------------------------------------

def note_rule_version(version: str, amendments: str):
    with _lock:
        db().execute("INSERT OR IGNORE INTO rule_versions(version,first_seen,amendments) "
                     "VALUES(?,?,?)", (version, now_utc(), amendments))
        db().commit()


def rule_versions():
    return db().execute("SELECT * FROM rule_versions ORDER BY first_seen").fetchall()


# ---- hypotheses + shadow tests ---------------------------------------------------------------

def add_hypothesis(title, rule, rule_ref, source, status, entry_ids=None, note=None) -> int:
    with _lock:
        cur = db().execute(
            "INSERT INTO hypotheses(created_at,title,rule,rule_ref,source,status,support,entry_ids,note) "
            "VALUES(?,?,?,?,?,?,1,?,?)",
            (now_utc(), title, rule, rule_ref, source, status, json.dumps(entry_ids or []), note))
        db().commit()
        return cur.lastrowid


def hypotheses(status=None):
    if status:
        qs = status if isinstance(status, (list, tuple)) else [status]
        return db().execute(f"SELECT * FROM hypotheses WHERE status IN ({','.join('?' * len(qs))}) "
                            "ORDER BY id", qs).fetchall()
    return db().execute("SELECT * FROM hypotheses ORDER BY id").fetchall()


def hypothesis(hid):
    return db().execute("SELECT * FROM hypotheses WHERE id=?", (hid,)).fetchone()


def support_hypothesis(hid, entry_id):
    h = hypothesis(hid)
    if not h:
        return
    ids = json.loads(h["entry_ids"] or "[]")
    if entry_id not in ids:
        ids.append(entry_id)
    with _lock:
        db().execute("UPDATE hypotheses SET support=support+1, entry_ids=? WHERE id=?",
                     (json.dumps(ids), hid))
        db().commit()


def set_hypothesis_status(hid, status, note=None):
    with _lock:
        db().execute("UPDATE hypotheses SET status=?, decided_at=?, note=COALESCE(?,note) WHERE id=?",
                     (status, now_utc(), note, hid))
        db().commit()


def add_shadow(entry_id, hyp_id, decision, size, changed, why):
    with _lock:
        db().execute("INSERT OR REPLACE INTO shadow(entry_id,hyp_id,decision,size,changed,why,at) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (entry_id, hyp_id, decision, size, 1 if changed else 0, why, now_utc()))
        db().commit()


def shadow_try(entry_id):
    with _lock:
        db().execute("UPDATE decisions SET shadow_tries=COALESCE(shadow_tries,0)+1 WHERE entry_id=?", (entry_id,))
        db().commit()


def shadow_todo(hyp_ids, since_iso, limit, max_tries=3):
    """Reviewed rows (newest first) that still need a shadow decision for some testing hypothesis.
    Rows whose shadow call failed `max_tries` times are left alone (one poison row must not
    stall the queue or burn a call every tick)."""
    if not hyp_ids:
        return []
    out = []
    rows = db().execute(
        "SELECT * FROM decisions WHERE decision IN ('TAKE','SKIP') AND entry_at>=? "
        "AND COALESCE(shadow_tries,0)<? ORDER BY entry_id DESC", (since_iso, max_tries)).fetchall()
    for r in rows:
        have = {x["hyp_id"] for x in db().execute(
            "SELECT hyp_id FROM shadow WHERE entry_id=?", (r["entry_id"],))}
        missing = [h for h in hyp_ids if h not in have]
        if missing:
            out.append((r, missing))
            if len(out) >= limit:
                break
    return out


def shadows_for(hyp_id):
    return db().execute(
        "SELECT s.*, d.r, d.decision AS real_decision, d.size AS real_size, d.entry_at, d.symbol "
        "FROM shadow s JOIN decisions d ON d.entry_id=s.entry_id WHERE s.hyp_id=? "
        "ORDER BY s.entry_id", (hyp_id,)).fetchall()


# ---- reporting -----------------------------------------------------------------------------

CSV_COLS = ["entry_id", "symbol", "entry_at_et", "session", "cascade", "direction", "mt_text",
            "mt_tf", "mt_cfg", "retrace", "play", "rules_version", "path", "jev_p_take", "entry", "stop", "target", "decision", "grade", "size",
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
                    r["direction"], r["mt_text"], r["mt_tf"], r["mt_cfg"], r["retrace"], r["play"],
                    r["rules_version"], r["path"], r["jev_p_take"], r["entry"],
                    r["stop"], r["target"], r["decision"], r["grade"], r["size"], r["confidence"],
                    r["hard_rule"], reasons, r["outcome"], r["r"], r["paper_r"],
                    to_et(r["closed_at"]), _lesson_text(r["lesson"]), r["screenshot_age_s"]])
    return buf.getvalue()


def write_csv_file():
    path = config.DATA_DIR / "trades.csv"
    path.write_text(export_csv())
    return path


def summarize(vals) -> dict:
    """n, win%, avg R, total R, max drawdown (R) for a list of R results in time order."""
    vals = [v for v in vals if v is not None]
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


def settled(since_iso=None):
    rows = [r for r in decisions(limit=100000, since_iso=since_iso) if r["r"] is not None]
    rows.sort(key=lambda x: x["entry_id"])
    return rows


def stats(since_iso=None):
    """Paper results: how the AI's TAKEs did vs what it SKIPPED (the filter's edge)."""
    rows = settled(since_iso)
    takes = [r for r in rows if r["decision"] == "TAKE"]
    skips = [r for r in rows if r["decision"] == "SKIP"]
    return {
        "paper_book": summarize([r["paper_r"] for r in takes]),
        "taken_as_full_size": summarize([r["r"] for r in takes]),
        "skipped_counterfactual": summarize([r["r"] for r in skips]),
        "all_engine_entries": summarize([r["r"] for r in rows]),
        "note": "r = fvg-mcp's scored result as if taken at full size; paper_r applies the "
                "agent's size (reduced = 0.5). The filter adds value if taken avg_r > all avg_r.",
    }
