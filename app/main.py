"""HTTP surface.

  GET  /health                 public, no data
  POST /screenshot?token=...   the Mac uploads a JPEG/PNG of the TradingView screen
  GET  /log.csv?token=...      every reviewed setup, ET times
  GET  /stats?token=...        paper results: taken vs skipped
  GET  /decisions?token=...    recent rows as JSON
  GET  /lessons?token=...      lessons + proposed rule changes
  GET  /report?token=...       strategy report: core vs agent vs hypotheses, breakdowns, spend
  GET  /                       dashboard (password login, 30-day cookie)
  /mcp                         read-only MCP connector so Claude can query the log
"""
import asyncio
import hashlib
import hmac
import json
import re
import time
import logging
import os
import threading
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import (FileResponse, HTMLResponse, JSONResponse, PlainTextResponse,
                                 RedirectResponse, Response)
from starlette.routing import Route

from pathlib import Path

from . import agent, config, jev, learning, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")


# ---- read-only MCP tools ---------------------------------------------------------------------
mcp = FastMCP(
    "Fractal Agent (paper)",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _row(r, full=False) -> dict:
    d = {k: r[k] for k in r.keys()}
    for k in ("reasons", "boosters", "chart_read", "context", "lesson", "jev", "news", "reeval"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    d["entry_at_et"] = store.to_et(d.get("entry_at"))
    d["closed_at_et"] = store.to_et(d.get("closed_at"))
    if full:
        d["screenshots"] = _shots_for(d["entry_id"])
    if not full:
        d.pop("context", None)
        d.pop("chart_read", None)
        d.pop("jev", None)
    return d


@mcp.tool()
def agent_status() -> dict:
    """Is the agent running, which models, when it last looped and last got a screenshot."""
    return agent.status()


@mcp.tool()
def paper_stats(days: float = 7) -> dict:
    """Paper results over the last `days`: the AI's TAKEs (paper book), what it SKIPPED
    (counterfactual), and every engine entry. avg_r, win%, total R, max drawdown in R."""
    since = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - days * 86400,
                                   tz=timezone.utc).isoformat()
    return store.stats(since)


@mcp.tool()
def decisions(limit: int = 25, symbol: str | None = None) -> list[dict]:
    """Most recent reviewed setups, newest first: decision, grade, size, reasons, outcome, R,
    lesson. Times in ET."""
    return [_row(r) for r in store.decisions(limit=limit, symbol=symbol)]


@mcp.tool()
def decision_detail(entry_id: int) -> dict:
    """Everything about one reviewed setup, including the chart read and the exact context the
    decision model saw."""
    rows = [r for r in store.decisions(limit=100000) if r["entry_id"] == entry_id]
    return _row(rows[0], full=True) if rows else {"error": "not found"}


@mcp.tool()
def lessons(limit: int = 30) -> list[dict]:
    """Lessons written after each settled trade, with any proposed rule change (needs Jake's
    approval before it goes into rules/amendments.md)."""
    out = []
    for r in store.recent_lessons(limit):
        d = {k: r[k] for k in r.keys()}
        d["created_at_et"] = store.to_et(d.pop("created_at"))
        out.append(d)
    return out


@mcp.tool()
def strategy_report(days: float = 30) -> dict:
    """The full picture over the last `days`: core strategy (every engine entry) vs the AI's
    paper book vs each shadow-tested hypothesis on the same trades; breakdowns by play, session,
    signal config, grade, booster and hard rule; results per rules version; Jev agreement;
    API spend. Every table has n, win%, avg R, total R, max drawdown."""
    return learning.report(days)


@mcp.tool()
def hypotheses() -> list[dict]:
    """Proposed strategy changes and their shadow-test results vs the agent and the core
    strategy on the same settled trades. Only Jake approves; approved ones go into
    rules/amendments.md."""
    return [learning.hypothesis_result(h) for h in store.hypotheses()]


def _shots_for(entry_id: int) -> dict:
    folder = config.DATA_DIR / "decision_shots"
    if not folder.exists():
        return {"at_decision": [], "at_exit": []}
    names = sorted(p.name for p in folder.glob(f"{entry_id}_*"))
    return {"at_decision": [n for n in names if "_exit_" not in n],
            "at_exit": [n for n in names if "_exit_" in n],
            "url": "/shot/<name>?token=AGENT_TOKEN (left window first; 5m charts left, 1m right)"}


@mcp.tool()
def chart_question(entry_id: int, question: str, at: str = "decision") -> dict:
    """Ask the vision model a specific question about the saved screenshot(s) of a trade
    (`at` = decision | exit): the lines, zones, gaps, Spotlight, colours as they were on the
    chart. Costs one vision call; paused when over the daily budget. For a text-only reviewer
    that cannot look at images itself."""
    if store.over_budget():
        return {"error": "over the daily budget; try later"}
    names = _shots_for(entry_id)["at_exit" if at == "exit" else "at_decision"]
    if not names:
        return {"error": "no screenshot saved for this trade at that moment"}
    folder = config.DATA_DIR / "decision_shots"
    images = [(folder / n).read_bytes() for n in names[:4]]
    prompt = ("You are reading TradingView screenshots (left window first; 5-minute charts on the left "
              "window, 1-minute on the right) for a futures trader using the Fractal Effects Market "
              "Translator and Spotlight indicators. Answer the question from what is VISIBLE only; say "
              "'not visible' when it is not. Reply with ONE JSON object: {\"answer\": \"...\", "
              "\"evidence\": [\"what on the chart supports it\"], \"confidence\": 0.0-1.0}\n\nQuestion: "
              + question[:800])
    try:
        from . import llm
        res = llm.read_chart(images, prompt)
    except Exception as e:
        return {"error": str(e)[:300]}
    return {"entry_id": entry_id, "at": at, "screenshots": names, **res}


@mcp.tool()
def rules_text(which: str = "all") -> dict:
    """The rule files the decider reads: amendments (highest priority), rulebook, live_rules.
    `which` = all | amendments | rulebook | live_rules."""
    from . import prompts
    names = {"amendments": "amendments.md", "rulebook": "rulebook.md", "live_rules": "live_rules.md"}
    out = {"rules_version": prompts.rules_version()}
    for k, f in names.items():
        if which in ("all", k):
            out[k] = prompts._read(f)
    return out


@mcp.tool()
def knowledge_search(query: str, k: int = 6) -> list[dict]:
    """Search the course transcripts, mini lessons, SOP and live-session transcripts (BM25) for
    the passages most relevant to `query`; the same index the decider uses."""
    from . import knowledge
    return knowledge.index().search(query[:400], k=max(1, min(int(k), 12)))


@mcp.tool()
def review_queue(reviewer: str = "hermes", limit: int = 10) -> list[dict]:
    """Settled paper trades (with their result) that `reviewer` has not reviewed yet, full detail:
    engine data, chart read, HTF FVGs, sister pair, management plan, mechanical and
    management-rules results, re-evaluation. Review them and POST /api/reviews."""
    return [_row(r, full=True) for r in store.review_queue(reviewer, limit)]


@mcp.tool()
def reviews(limit: int = 30, entry_id: int | None = None) -> list[dict]:
    """Reviews filed by outside reviewers (e.g. Hermes): verdict, what to do better, exit notes,
    proposal."""
    out = []
    for r in store.reviews(limit, entry_id):
        d = {k: r[k] for k in r.keys()}
        d["at_et"] = store.to_et(d.pop("at"))
        try:
            d["raw"] = json.loads(d["raw"]) if d["raw"] else None
        except ValueError:
            pass
        out.append(d)
    return out


@mcp.tool()
def api_spend(days: float = 30) -> dict:
    """OpenRouter spend (USD) by purpose and model, plus a per-day series."""
    since = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - days * 86400,
                                   tz=timezone.utc).isoformat()
    return {**store.spend(since), "by_day": store.spend_by_day(int(days))}


# ---- plain HTTP routes ---------------------------------------------------------------------

COOKIE = "fa_session"
SESSION_DAYS = 30


def _sign(exp: int) -> str:
    key = (config.DASHBOARD_PASSWORD + "|" + config.AGENT_TOKEN).encode()
    return hmac.new(key, str(exp).encode(), hashlib.sha256).hexdigest()


def _cookie_ok(request: Request) -> bool:
    if not config.DASHBOARD_PASSWORD:
        return False
    raw = request.cookies.get(COOKIE, "")
    exp, _, sig = raw.partition(".")
    if not exp.isdigit() or int(exp) < time.time():
        return False
    return hmac.compare_digest(sig.encode(), _sign(int(exp)).encode())


def _authed(request: Request) -> bool:
    if _cookie_ok(request):
        return True
    if not config.AGENT_TOKEN:
        return False   # closed until a token is configured
    tok = request.query_params.get("token") or request.headers.get("x-agent-token", "")
    return hmac.compare_digest(tok.encode(), config.AGENT_TOKEN.encode())


async def health(request: Request):
    return JSONResponse({"ok": True, **agent.status()})


async def screenshot(request: Request):
    if not _authed(request):
        return PlainTextResponse("unauthorized", status_code=401)
    body = await request.body()
    if not body or len(body) > 15_000_000:
        return PlainTextResponse("empty or too large", status_code=400)
    ext = "png" if body[:4] == b"\x89PNG" else "jpg"
    shots = config.DATA_DIR / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    # one upload per TradingView window: ?batch=<id>&part=<n> groups them into one set
    batch = re.sub(r"[^0-9A-Za-z_-]", "", request.query_params.get("batch", ""))[:40] or None
    part = int(request.query_params.get("part", "0") or 0) if batch else None
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + (f"_{part}" if batch else "") + f".{ext}"
    (shots / name).write_bytes(body)
    kind = request.query_params.get("kind") or ("window" if batch else "screen")
    store.add_screenshot(name, len(body), batch, part, kind[:20])
    # keep the folder small: only the newest 400 files (~3h at one every 30s)
    files = sorted(shots.iterdir())
    for old in files[:-400]:
        old.unlink(missing_ok=True)
    return JSONResponse({"ok": True, "file": name, "bytes": len(body)})


async def capture_status(request: Request):
    """The Mac reports why it sent nothing (TradingView tab hidden / not open / capture failed)."""
    if not _authed(request):
        return PlainTextResponse("unauthorized", status_code=401)
    state = re.sub(r"[^a-z_]", "", request.query_params.get("state", ""))[:30]
    store.kv_set("capture_status", {"state": state, "at": store.now_utc()})
    return JSONResponse({"ok": True})


async def log_csv(request: Request):
    if not _authed(request):
        return PlainTextResponse("unauthorized", status_code=401)
    return Response(store.export_csv(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=fractal_agent_log.csv"})


async def stats_route(request: Request):
    if not _authed(request):
        return PlainTextResponse("unauthorized", status_code=401)
    return JSONResponse(store.stats())


async def decisions_route(request: Request):
    if not _authed(request):
        return PlainTextResponse("unauthorized", status_code=401)
    n = int(request.query_params.get("limit", "50"))
    return JSONResponse([_row(r) for r in store.decisions(limit=n)])


async def lessons_route(request: Request):
    if not _authed(request):
        return PlainTextResponse("unauthorized", status_code=401)
    return JSONResponse(lessons(int(request.query_params.get("limit", "50"))))


async def report_route(request: Request):
    if not _authed(request):
        return PlainTextResponse("unauthorized", status_code=401)
    return JSONResponse(learning.report(float(request.query_params.get("days", "30"))))


# ---- dashboard -------------------------------------------------------------------------------

DASH_HTML = Path(__file__).resolve().parent / "dashboard.html"
LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Fractal Agent</title>
<style>:root{color-scheme:dark}body{margin:0;min-height:100vh;display:grid;place-items:center;
background:#121212;color:#eee;font:16px system-ui,-apple-system,sans-serif}
form{background:#1c1c1b;padding:28px;border-radius:12px;width:min(320px,90vw);display:grid;gap:12px}
input,button{font:inherit;padding:10px 12px;border-radius:8px;border:1px solid #3a3a38;background:#121212;color:#eee}
button{background:#3987e5;border:0;color:#fff;cursor:pointer}p{margin:0;color:#e66767;font-size:14px}
</style></head><body><form method="post" action="/login"><strong>Fractal Agent</strong>
<input type="password" name="password" placeholder="Password" autofocus autocomplete="current-password">
<button>Log in</button>%s</form></body></html>"""


async def dashboard(request: Request):
    if not _cookie_ok(request):
        return HTMLResponse(LOGIN_HTML % "", headers={"Cache-Control": "no-store"})
    # no-store: a cached copy of an older page would keep running old JavaScript against new data
    return HTMLResponse(DASH_HTML.read_text(), headers={"Cache-Control": "no-store"})


async def login(request: Request):
    form = await request.form()
    pw = str(form.get("password", ""))
    if not config.DASHBOARD_PASSWORD or not hmac.compare_digest(pw.encode(), config.DASHBOARD_PASSWORD.encode()):
        await asyncio.sleep(1)   # slow down guessing
        return HTMLResponse(LOGIN_HTML % "<p>Wrong password</p>", status_code=401)
    exp = int(time.time()) + SESSION_DAYS * 86400
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE, f"{exp}.{_sign(exp)}", max_age=SESSION_DAYS * 86400, httponly=True,
                    secure=request.url.scheme == "https" or
                    request.headers.get("x-forwarded-proto") == "https", samesite="lax")
    return resp


async def logout(request: Request):
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


def _curve(rows, key):
    cum, out = 0.0, []
    for r in rows:
        v = r[key] if r[key] is not None else 0.0
        cum += v
        out.append(round(cum, 3))
    return out


async def api_dashboard(request: Request):
    if not _authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    days = float(request.query_params.get("days", "30"))
    rep_ = learning.report(days)
    since = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - days * 86400,
                                   tz=timezone.utc).isoformat()
    settled = store.settled(since)
    today = datetime.now(config.ET).strftime("%Y-%m-%d")
    today_rows = [r for r in settled if store.to_et(r["entry_at"]).startswith(today)]
    feed = []
    for r in store.decisions(limit=60):
        d = _row(r)
        d["chart_read"] = json.loads(r["chart_read"]) if r["chart_read"] else None
        d["jev"] = json.loads(r["jev"]) if r["jev"] else None
        d["news"] = json.loads(r["news"]) if r["news"] else None
        d["reeval"] = json.loads(r["reeval"]) if r["reeval"] else None
        d["reviews"] = [{"reviewer": v["reviewer"], "verdict": v["verdict"], "summary": v["summary"],
                         "exit_notes": v["exit_notes"], "proposal": v["proposal"], "at_et": store.to_et(v["at"])}
                        for v in store.reviews(5, r["entry_id"])]
        try:
            ctx = (json.loads(r["context"]) or {}) if r["context"] else {}
            d["plan"] = ctx.get("_plan")
            d["read"] = ctx.get("_read")
        except ValueError:
            d["plan"] = d["read"] = None
        d["shots"] = sorted(p.name for p in (config.DATA_DIR / "decision_shots").glob(f"{r['entry_id']}_*"))
        feed.append(d)
    since_month = datetime.now(config.ET).replace(day=1, hour=0, minute=0, second=0).astimezone(timezone.utc).isoformat()
    since_today = datetime.now(config.ET).replace(hour=0, minute=0, second=0).astimezone(timezone.utc).isoformat()
    shot = store.latest_screenshot_set()
    return JSONResponse({
        "status": agent.status(),
        "latest_shots": [s["file"] for s in shot],
        "today": {"agent": store.summarize([r["paper_r"] for r in today_rows if r["decision"] == "TAKE"]),
                  "core": store.summarize([r["r"] for r in today_rows]),
                  "reviewed": sum(1 for r in store.decisions(limit=500, since_iso=since_today))},
        "spend": {"today": store.spend(since_today)["total_usd"],
                  "month": store.spend(since_month)["total_usd"],
                  "window": rep_["spend"], "by_day": store.spend_by_day(int(max(days, 1)))},
        "curve": {"labels": [store.to_et(r["entry_at"])[:16] for r in settled],
                  "core": _curve(settled, "r"), "agent": _curve(settled, "paper_r")},
        "report": rep_,
        "feed": feed,
        "hypotheses_other": [learning.hypothesis_result(h)
                             for h in store.hypotheses(["rejected", "retired"])],
        "lessons": lessons(40),
        "scans": [{**{k: r[k] for k in r.keys()}, "at_et": store.to_et(r["at"]),
                   "reasons": json.loads(r["reasons"] or "[]")} for r in store.scans(40)],
        "backtest": _backtest(),
        "jev_playbook": jev.playbook()["readable"],
        "vision": _vision_stats(since),
        "rule_versions": [{"version": v["version"], "first_seen_et": store.to_et(v["first_seen"]),
                           "amendments": v["amendments"]} for v in store.rule_versions()],
    }, headers={"Cache-Control": "no-store"})


BACKTEST = Path(__file__).resolve().parent.parent / "reports" / "backtest_latest.json"


def _backtest():
    try:
        return json.loads(BACKTEST.read_text()) if BACKTEST.exists() else None
    except ValueError:
        return None


def _vision_stats(since_iso):
    rows = [r for r in store.decisions(limit=100000, since_iso=since_iso) if r["vision_score"] is not None]
    if not rows:
        return {"n": 0}
    good = sum(1 for r in rows if r["vision_score"] >= 0.7)
    return {"n": len(rows), "trusted_pct": round(100 * good / len(rows), 1),
            "avg_score": round(sum(r["vision_score"] for r in rows) / len(rows), 2),
            "notes": [r["vision_note"] for r in rows[:8]]}


async def api_hypothesis(request: Request):
    if not _cookie_ok(request) and not _authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    hid = int(request.path_params["hid"])
    body = await request.json()
    status = body.get("status")
    if status not in ("approved", "rejected", "retired", "testing") or not store.hypothesis(hid):
        return JSONResponse({"error": "bad request"}, status_code=400)
    store.set_hypothesis_status(hid, status, (body.get("note") or None))
    return JSONResponse({"ok": True, "id": hid, "status": status})


async def propose_hypothesis(request: Request):
    """POST /api/hypotheses/propose {title, rule, rule_ref?, note?} with the agent token: an
    outside reviewer (e.g. a Hermes Agent review job) files a proposal. It enters the same
    shadow-test pipeline as a lesson proposal; nothing changes the rules without Jake."""
    if not _authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({"error": "bad json"}, status_code=400)
    rule, title = str(body.get("rule") or "").strip(), str(body.get("title") or "").strip()
    if not rule or not title or len(rule) > 1500:
        return JSONResponse({"error": "title and rule (IF ... THEN ...) required"}, status_code=400)
    source = re.sub(r"[^a-z0-9_-]", "", str(body.get("source") or "hermes").lower())[:20] or "external"
    hid = learning.register_proposal({"proposal": rule, "proposal_title": title[:80],
                                      "rule_ref": body.get("rule_ref")}, entry_id=0, source=source,
                                     note=(body.get("note") or None))
    return JSONResponse({"ok": True, "hypothesis_id": hid})


async def review_queue_route(request: Request):
    if not _authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(review_queue(request.query_params.get("reviewer", "hermes"),
                                     int(request.query_params.get("limit", "10"))))


async def post_review(request: Request):
    """POST /api/reviews {entry_id, reviewer, verdict, summary, exit_notes, proposal?, proposal_title?}
    (token). A proposal is also filed as a hypothesis so it gets shadow-tested."""
    if not _authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
        entry_id = int(body["entry_id"])
    except (ValueError, KeyError, TypeError):
        return JSONResponse({"error": "entry_id required"}, status_code=400)
    reviewer = re.sub(r"[^a-z0-9_-]", "", str(body.get("reviewer") or "hermes").lower())[:20] or "external"
    verdict = str(body.get("verdict") or "")[:20]
    store.add_review(entry_id, reviewer, verdict, str(body.get("summary") or "")[:2000],
                     str(body.get("exit_notes") or "")[:2000], body.get("proposal"), body)
    hid = None
    if body.get("proposal"):
        hid = learning.register_proposal({"proposal": body["proposal"], "proposal_title": body.get("proposal_title"),
                                          "rule_ref": body.get("rule_ref")}, entry_id, source=reviewer)
    return JSONResponse({"ok": True, "hypothesis_id": hid})


async def shot_file(request: Request):
    if not _authed(request):
        return PlainTextResponse("unauthorized", status_code=401)
    name = request.path_params["name"]
    if not re.fullmatch(r"[0-9A-Za-z_.-]+", name) or ".." in name:
        return PlainTextResponse("bad name", status_code=400)
    for folder in ("decision_shots", "shots"):
        p = config.DATA_DIR / folder / name
        if p.exists():
            return FileResponse(p, headers={"Cache-Control": "private, max-age=86400"})
    return PlainTextResponse("not found", status_code=404)


app = mcp.streamable_http_app()
app.router.routes.extend([
    Route("/health", health),
    Route("/screenshot", screenshot, methods=["POST"]),
    Route("/capture_status", capture_status, methods=["POST"]),
    Route("/log.csv", log_csv),
    Route("/stats", stats_route),
    Route("/decisions", decisions_route),
    Route("/lessons", lessons_route),
    Route("/report", report_route),
    Route("/", dashboard),
    Route("/login", login, methods=["POST"]),
    Route("/logout", logout),
    Route("/api/dashboard", api_dashboard),
    Route("/api/hypotheses/{hid:int}", api_hypothesis, methods=["POST"]),
    Route("/api/hypotheses/propose", propose_hypothesis, methods=["POST"]),
    Route("/api/review_queue", review_queue_route),
    Route("/api/reviews", post_review, methods=["POST"]),
    Route("/shot/{name}", shot_file),
])

# ---- background loop ---------------------------------------------------------------------
_stop = threading.Event()
if os.environ.get("RUN_LOOP", "1") == "1":
    store.db()
    threading.Thread(target=agent.run_forever, args=(_stop,), daemon=True, name="agent").start()
    log.info("agent loop started: symbols=%s paper_only=True", config.SYMBOLS)
