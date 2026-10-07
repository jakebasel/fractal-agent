"""HTTP surface.

  GET  /health                 public, no data
  POST /screenshot?token=...   the Mac uploads a JPEG/PNG of the TradingView screen
  GET  /log.csv?token=...      every reviewed setup, ET times
  GET  /stats?token=...        paper results: taken vs skipped
  GET  /decisions?token=...    recent rows as JSON
  GET  /lessons?token=...      lessons + proposed rule changes
  /mcp                         read-only MCP connector so Claude can query the log
"""
import hmac
import json
import logging
import os
import threading
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from . import agent, config, store

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
    for k in ("reasons", "boosters", "chart_read", "context", "lesson"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    d["entry_at_et"] = store.to_et(d.get("entry_at"))
    d["closed_at_et"] = store.to_et(d.get("closed_at"))
    if not full:
        d.pop("context", None)
        d.pop("chart_read", None)
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


# ---- plain HTTP routes ---------------------------------------------------------------------

def _authed(request: Request) -> bool:
    if not config.AGENT_TOKEN:
        return False   # closed until a token is configured
    tok = request.query_params.get("token") or request.headers.get("x-agent-token", "")
    return hmac.compare_digest(tok, config.AGENT_TOKEN)


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
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f".{ext}"
    (shots / name).write_bytes(body)
    store.add_screenshot(name, len(body))
    # keep the folder small: only the newest 400 files (~3h at one every 30s)
    files = sorted(shots.iterdir())
    for old in files[:-400]:
        old.unlink(missing_ok=True)
    return JSONResponse({"ok": True, "file": name, "bytes": len(body)})


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


app = mcp.streamable_http_app()
app.router.routes.extend([
    Route("/health", health),
    Route("/screenshot", screenshot, methods=["POST"]),
    Route("/log.csv", log_csv),
    Route("/stats", stats_route),
    Route("/decisions", decisions_route),
    Route("/lessons", lessons_route),
])

# ---- background loop ---------------------------------------------------------------------
_stop = threading.Event()
if os.environ.get("RUN_LOOP", "1") == "1":
    store.db()
    threading.Thread(target=agent.run_forever, args=(_stop,), daemon=True, name="agent").start()
    log.info("agent loop started: symbols=%s paper_only=True", config.SYMBOLS)
