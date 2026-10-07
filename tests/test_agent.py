"""End-to-end test with a fake fvg-mcp (a real FastMCP server on localhost) and a fake LLM.

Run:  .venv/bin/python tests/test_agent.py
No network, no API spend.
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = tempfile.mkdtemp()
os.environ.update(DATA_DIR=TMP, RUN_LOOP="0", OPENROUTER_API_KEY="test", AGENT_TOKEN="tok",
                  SYMBOLS="MNQ1!,MES1!", MAX_ENTRY_AGE_S="300")

import uvicorn  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

# ---------------------------------------------------------------- fake fvg-mcp
FAKE = {"entries": {"MNQ1!": [], "MES1!": []}}
fake = FastMCP("fake fvg", stateless_http=True, json_response=True,
               transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


@fake.tool()
def entries(symbol: str | None = None, limit: int = 20) -> list[dict]:
    return list(reversed(FAKE["entries"].get(symbol, [])))[:limit]


@fake.tool()
def setups(symbol: str) -> dict:
    return {"symbol": symbol, "setups": [{"cascade": "2-stage", "direction": "bull",
                                          "mt": "Upper Double Break", "status": "armed_wait"}]}


@fake.tool()
def recent_events(symbol: str | None = None, source: str | None = None,
                  limit: int = 25) -> list[dict]:
    return [{"received_at": datetime.now(timezone.utc).isoformat(), "tf": "5m",
             "text": "Upper Double Break", "price": 31400}]


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = free_port()
server = uvicorn.Server(uvicorn.Config(fake.streamable_http_app(), port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(50):
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close()
        break
    except OSError:
        time.sleep(0.1)
os.environ["FVG_MCP_URL"] = f"http://127.0.0.1:{PORT}/mcp"

from app import agent, config, llm, store  # noqa: E402
from app.mcp_client import FVG  # noqa: E402

config.FVG_MCP_URL = os.environ["FVG_MCP_URL"]

# ---------------------------------------------------------------- fake LLM
CALLS = []


def fake_post(model, messages, max_tokens=1500, temperature=0.1):
    CALLS.append(model)
    sysmsg = messages[0]["content"] if isinstance(messages[0]["content"], str) else ""
    if model == config.VISION_MODEL:
        return json.dumps({"charts": [{"symbol": "MNQ", "timeframe": "5m"}], "readability": "good"})
    if "review a finished PAPER trade" in sysmsg:
        return '```json\n{"verdict":"right_take","lesson":"DB retrace into purple worked","rule_ref":"§3","proposal":null}\n```'
    assert "RULEBOOK" in sysmsg and "Hard rules" in sysmsg, "rulebook not in prompt"
    return 'Sure. {"decision":"TAKE","grade":"B","size":"full","confidence":0.6,"hard_rule":null,' \
           '"boosters":["DB"],"reasons":["§3 DB continuation"]}'


llm._post = fake_post


def mk_entry(i, sym="MNQ1!", age_s=10, trend_fallback=False, cascade="2-stage", r=None):
    at = (datetime.now(timezone.utc) - timedelta(seconds=age_s)).isoformat()
    detail = {"session": "london", "in_window": True, "mt_cfg": "DB", "retrace": "deep",
              "trend_fallback": trend_fallback, "signal_at": at,
              "mt_seq": [{"text": "Upper Double Break"}], "stages": [], "stops": []}
    return {"id": i, "at": at, "symbol": sym, "cascade": cascade, "direction": "bull",
            "entry": 100.0, "stop": 90.0, "target": 130.0, "mt_text": "Upper Double Break",
            "mt_tf": "5m", "mt_price": 99.0, "detail": json.dumps(detail),
            "f_pnl_r": r, "f_outcome": None if r is None else "2R + runner to 3R",
            "f_close_bar": None if r is None else int(time.time() * 1000), "f_exit": 130.0}


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


fvg = FVG()

# 1. MCP client round-trip against a real FastMCP stateless server
ok(fvg.setups("MNQ1!")["symbol"] == "MNQ1!", "MCP client unwraps dict results")
ok(isinstance(fvg.mt_events("MNQ1!"), list), "MCP client unwraps list results")

# 2. first tick sets a baseline and does NOT review history
FAKE["entries"]["MNQ1!"] = [mk_entry(1, age_s=5)]
agent.tick(fvg)
ok(not store.seen(1), "history before start-up is not reviewed")

# 3. new entry -> reviewed with a screenshot read; B grade forced to reduced size
shots = Path(TMP) / "shots"
shots.mkdir(exist_ok=True)
(shots / "a.jpg").write_bytes(b"\xff\xd8fakejpeg")
store.add_screenshot("a.jpg", 10)
FAKE["entries"]["MNQ1!"].append(mk_entry(2))
agent.tick(fvg)
row = store.decisions(limit=1)[0]
ok(row["decision"] == "TAKE" and row["size"] == "reduced", f"grade B TAKE is reduced size ({row['size']})")
ok(row["chart_read"] is not None and config.VISION_MODEL in CALLS, "vision model read the screenshot")

# 4. ND entry is skipped by code without any model call
n_calls = len(CALLS)
FAKE["entries"]["MNQ1!"].append(mk_entry(3, trend_fallback=True))
agent.tick(fvg)
r3 = [r for r in store.decisions() if r["entry_id"] == 3][0]
ok(r3["decision"] == "SKIP" and "ND" in r3["hard_rule"] and len(CALLS) == n_calls,
   "ND entry skipped by code, no model call")

# 5. stale entry -> MISSED; Gold Strategy ignored
FAKE["entries"]["MNQ1!"].append(mk_entry(4, age_s=4000))
FAKE["entries"]["MNQ1!"].append(mk_entry(5, cascade="Gold Strategy"))
agent.tick(fvg)
ok([r for r in store.decisions() if r["entry_id"] == 4][0]["decision"] == "MISSED", "stale entry logged as MISSED")
ok(not store.seen(5), "Gold Strategy rows ignored")

# 6. outcome arrives -> paper_r = r * 0.5, lesson written
FAKE["entries"]["MNQ1!"][1] = mk_entry(2, r=2.5)
agent.tick(fvg)
row = [r for r in store.decisions() if r["entry_id"] == 2][0]
ok(row["r"] == 2.5 and row["paper_r"] == 1.25, f"settled: r={row['r']} paper_r={row['paper_r']}")
ok(len(store.recent_lessons(5)) == 1, "lesson stored")

# 7. CSV + stats
csv_text = (Path(TMP) / "trades.csv").read_text()
ok("entry_id,symbol,entry_at_et" in csv_text and " ET" in csv_text, "CSV written with ET times")
st = store.stats()
ok(st["paper_book"]["n"] == 1 and st["paper_book"]["total_r"] == 1.25, "stats: paper book")

# 8. HTTP + MCP surface of the agent itself
from starlette.testclient import TestClient  # noqa: E402
from app import main  # noqa: E402

with TestClient(main.app) as c:
    ok(c.get("/log.csv").status_code == 401, "log.csv needs the token")
    ok(c.get("/log.csv?token=tok").status_code == 200, "log.csv with token")
    ok(c.post("/screenshot?token=tok", content=b"\x89PNGxxxx").json()["ok"], "screenshot upload")
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": "paper_stats", "arguments": {"days": 7}}},
               headers={"Accept": "application/json, text/event-stream"})
    ok(r.status_code == 200 and "paper_book" in r.text, "agent MCP tool paper_stats works")

print("all tests passed")
server.should_exit = True
