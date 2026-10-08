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
                  SYMBOLS="MNQ1!,MES1!", MAX_ENTRY_AGE_S="300", DASHBOARD_PASSWORD="pw", BUILTIN_LESSONS="1")

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

from app import agent, config, learning, llm, rules_code, store  # noqa: E402
from app.mcp_client import FVG  # noqa: E402

config.FVG_MCP_URL = os.environ["FVG_MCP_URL"]

# ---------------------------------------------------------------- fake LLM
CALLS = []
PURPOSES = []


def fake_post(model, messages, max_tokens=1500, temperature=0.1, purpose="other"):
    CALLS.append(model)
    PURPOSES.append(purpose)
    sysmsg = messages[0]["content"] if isinstance(messages[0]["content"], str) else ""
    if model == config.VISION_MODEL:
        return json.dumps({"charts": [{"symbol": "MNQ", "timeframe": "5m"}], "readability": "good"})
    if "review a finished PAPER trade" in sysmsg:
        return '```json\n{"verdict":"right_take","lesson":"DB retrace into purple worked","rule_ref":"§3",' \
               '"proposal":"IF the DB retrace taps a purple zone THEN TAKE full size","proposal_title":"Purple zone DB full"}\n```'
    if "file proposed rule changes" in sysmsg:
        return '{"same_as": null, "title": "Purple zone DB full"}'
    if "re-deciding a PAPER trade" in sysmsg:
        ids = [h["id"] for h in json.loads(messages[1]["content"])["hypotheses"]]
        return json.dumps({str(i): {"decision": "SKIP", "size": "none", "applies": True, "why": "test"}
                           for i in ids})
    assert "RULEBOOK" in sysmsg and "Hard rules" in sysmsg, "rulebook not in prompt"
    return 'Sure. {"decision":"TAKE","play_kind":"continuation","grade":"B","size":"full","confidence":0.6,"hard_rule":null,' \
           '"boosters":["DB"],"reasons":["§3 DB continuation"]}'


llm._post = fake_post

JEV_CALLS = []


def fake_system_one(state, questions, purpose="jev"):
    JEV_CALLS.append(sorted(questions))
    ans = {k: {"type": "noul", "noul": 0.9 if k.startswith(("must_", "boost_", "amend")) else 0.1}
           for k in questions if questions[k]["type"] == "noul"}
    ans["take"] = {"type": "choice", "choice": "TAKE", "probabilities": {"TAKE": 0.7, "SKIP": 0.3}}
    ans["grade"] = {"type": "choice", "choice": "A", "probabilities": {"A": 1.0}}
    ans["play"] = {"type": "choice", "choice": "continuation", "probabilities": {}}
    store.log_api_call(purpose, "typesafe/jev-1.13", 400, 0, 0.00002, 90, True)
    return {"answers": ans, "model": "jev-1.13.0", "ms": 90}


llm.system_one = fake_system_one
NEWS = {"events": []}
rules_code.news_events = lambda: NEWS["events"]


def mk_entry(i, sym="MNQ1!", age_s=10, trend_fallback=False, cascade="2-stage", r=None):
    at = (datetime.now(timezone.utc) - timedelta(seconds=age_s)).isoformat()
    # "nypm" has no clock rule, so the fixture decides the same at any time of day
    detail = {"session": "nypm", "in_window": True, "mt_cfg": "DB", "retrace": "deep",
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
n_calls = len(PURPOSES)
FAKE["entries"]["MNQ1!"].append(mk_entry(3, trend_fallback=True))
agent.tick(fvg)
r3 = [r for r in store.decisions() if r["entry_id"] == 3][0]
ok(r3["decision"] == "SKIP" and "ND" in r3["hard_rule"] and r3["play"] == "5m DB continuation"
   and not {"decision", "vision"} & set(PURPOSES[n_calls:]),
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

# 9. new in v2: hard rules in code, news filter, Jev shadow, hypotheses + shadow tests, spend,
#    dashboard login, multi-window screenshots, strategy report
from datetime import datetime as _dt  # noqa: E402

e = mk_entry(6)
d = json.loads(e["detail"]); d["retrace"] = "none"; e["detail"] = json.dumps(d)
ok(rules_code.hard_rule(e, d, _dt.now(timezone.utc))[0].startswith("§2.6"), "code rule: DB with no retrace skipped")
NEWS["events"] = [{"title": "CPI m/m", "at": _dt.now(timezone.utc) + timedelta(minutes=20)}]
e = mk_entry(7)
fired, info = rules_code.hard_rule(e, json.loads(e["detail"]), _dt.now(timezone.utc))
ok(fired and "news bracket" in fired and "20 min before" in fired, f"code rule: inside the news bracket ({fired})")
NEWS["events"] = [{"title": "CPI m/m", "at": _dt.now(timezone.utc) + timedelta(hours=3)}]
fired, info = rules_code.hard_rule(e, json.loads(e["detail"]), _dt.now(timezone.utc))
ok(fired is None and info["today"], "code rule: same day but outside the bracket trades normally")
NEWS["events"] = []
e = mk_entry(9); d = json.loads(e["detail"]); d["in_window"] = False; d["mt_cfg"] = "2DB"; e["detail"] = json.dumps(d)
e["mt_text"] = "Lower Double Break (2DB)"
fired, _ = rules_code.hard_rules(e, d, _dt.now(timezone.utc))
ok(fired[0].startswith("§2.4 2DB") and not any("window" in f for f in fired), f"2DB reported; engine window flag is no longer a skip ({fired})")

row2 = [r for r in store.decisions() if r["entry_id"] == 2][0]
ok(row2["jev_p_take"] == 0.7 and json.loads(row2["jev"])["play"] == "continuation", "Jev shadow score stored on the row")
ok(row2["rules_version"] and row2["path"] == "model" and row2["play"] == "5m DB continuation", f"row carries rules_version, path, play ({row2['play']})")
ok(JEV_CALLS and "take" in JEV_CALLS[0] and "hard_5" in JEV_CALLS[0] and any(k.startswith("must_") for k in JEV_CALLS[0])
   and any(k.startswith("boost_") for k in JEV_CALLS[0]), "Jev playbook asks hard rules, must-haves and boosters")
jv2 = json.loads(row2["jev"])
ok(jv2["boosters_present"] >= 1 and jv2["must_haves_missing"] == [] and jv2["amendments_ok"] == 0.9, "Jev playbook answers summarised")

hyps = store.hypotheses()
ok(any(h["source"] == "lesson" and h["status"] == "testing" for h in hyps), "lesson proposal became a testing hypothesis")
ok(any(h["source"] == "engine-data" for h in hyps), "seed hypotheses present")
sh = store.shadows_for([h for h in hyps if h["source"] == "lesson"][0]["id"])
ok(sh and sh[0]["decision"] == "SKIP" and sh[0]["changed"] == 1, "shadow decision recorded for a settled trade")
rep = learning.report(30)
hres = [h for h in rep["hypotheses"] if h["source"] == "lesson"][0]
ok(hres["books_same_trades"]["agent"]["total_r"] == 1.25 and hres["books_same_trades"]["with_change"].get("n") == 0
   and hres["delta_total_r_vs_agent"] == -1.25, "hypothesis compared on the same trades")
ok(rep["books"]["core_strategy_all_engine_entries"]["n"] == 1 and rep["core_by_play"][0]["group"] == "5m DB continuation"
   and rep["core_by_timeframe_signal"][0]["group"] == "5m DB", "report breakdowns by play and timeframe x signal")
ok(store.spend()["calls"] >= 1 and store.spend()["total_usd"] > 0, "API spend logged")

# Jev gate mode: a sure hard rule skips without DeepSeek
config.JEV_MODE = "gate"
def sure_jev(state, questions, purpose="jev"):
    ans = {k: {"type": "noul", "noul": 0.97 if k == "hard_7" else 0.05} for k in questions if questions[k]["type"] == "noul"}
    ans["take"] = {"type": "choice", "choice": "SKIP", "probabilities": {"TAKE": 0.1, "SKIP": 0.9}}
    ans["grade"] = {"type": "choice", "choice": "C", "probabilities": {}}
    ans["play"] = {"type": "choice", "choice": "other", "probabilities": {}}
    return {"answers": ans, "model": "jev-1.13.0", "ms": 80}
llm.system_one = sure_jev
n_calls = len(PURPOSES)
FAKE["entries"]["MNQ1!"].append(mk_entry(8))
agent.tick(fvg)
r8 = [r for r in store.decisions() if r["entry_id"] == 8][0]
ok(r8["decision"] == "SKIP" and r8["path"] == "jev" and "§2.7" in r8["hard_rule"]
   and "decision" not in PURPOSES[n_calls:], "Jev gate skips a sure hard rule without DeepSeek")
config.JEV_MODE = "shadow"; llm.system_one = fake_system_one

c = TestClient(main.app)   # no lifespan: the MCP session manager only starts once
if True:
    ok(c.get("/").status_code == 200 and "password" in c.get("/").text, "dashboard shows login")
    ok(c.get("/api/dashboard").status_code == 401, "dashboard API closed without login")
    r = c.post("/login", data={"password": "wrong"})
    ok(r.status_code == 401, "wrong password rejected")
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    ok(r.status_code == 303 and "fa_session" in r.headers.get("set-cookie", ""), "login sets the session cookie")
    dash = c.get("/api/dashboard?days=30")
    ok(dash.status_code == 200 and dash.json()["report"]["hypotheses"], "dashboard API with cookie")
    ok("Cumulative R" in c.get("/").text, "dashboard page served after login")
    hid = hyps[0]["id"]
    ok(c.post(f"/api/hypotheses/{hid}", json={"status": "approved"}).json()["status"] == "approved"
       and store.hypothesis(hid)["status"] == "approved", "hypothesis approved from the dashboard")
    c.post("/screenshot?token=tok&batch=b1&part=0", content=b"\xff\xd8left")
    c.post("/screenshot?token=tok&batch=b1&part=1", content=b"\xff\xd8right")
    sset = store.latest_screenshot_set()
    ok(len(sset) == 2 and sset[0]["part"] == 0, "two-window screenshot batch grouped, left first")
    c.post("/screenshot?token=tok&batch=b2&part=0&kind=vps&layout=four+charts+in+a+grid", content=b"\xff\xd8grid")
    ok(store.kv_get("screen_layout:vps") == "four charts in a grid", "uploader's layout text stored per kind")
    from app import prompts
    ok("four charts in a grid" in prompts.vision_prompt(store.kv_get("screen_layout:vps"))
       and config.SCREEN_LAYOUT in prompts.vision_prompt(), "vision prompt uses the uploader's layout when given")
    ok(TestClient(main.app).get(f"/shot/{sset[0]['file']}").status_code == 401 and c.get(f"/shot/{sset[0]['file']}").status_code == 200, "screenshot file needs login")
    ok("core_by_play" in main.strategy_report(30) and main.hypotheses() and "by_day" in main.api_spend(7),
       "MCP tools strategy_report / hypotheses / api_spend work")

# 10. scanner, vision sanity, screenshot kind, budget guard, backtest report
from app import scanner  # noqa: E402
cr = {"charts": [{"symbol": "MNQ", "timeframe": "5m", "last_price": 100.2, "white_lines": [{"label": "DB", "price": 99}]}]}
sc, note = scanner.sanity_check(cr, {"symbol": "MNQ1!", "entry": 100.0})
ok(sc == 1.0 and "within" in note, f"vision sanity: price matches ({note})")
sc, note = scanner.sanity_check(cr, {"symbol": "MES1!", "entry": 50.0})
ok(sc == 0.0, "vision sanity: symbol not on screen")
from datetime import datetime as _dt2  # noqa: E402
import zoneinfo  # noqa: E402
ET = zoneinfo.ZoneInfo("America/New_York")
ok(scanner.in_window(_dt2(2026, 10, 7, 9, 40, tzinfo=ET)) and not scanner.in_window(_dt2(2026, 10, 7, 12, 0, tzinfo=ET)),
   "scanner windows (ET)")
def fake_scan_post(model, messages, max_tokens=1500, temperature=0.1, purpose="other"):
    if purpose == "scan":
        PURPOSES.append(purpose)
        return '{"setups":[{"symbol":"MES1!","play":"5m DB reversal set up","direction":"bear","stage":"forming","confidence":0.6,"reasons":["red reversal zone printed"],"engine_has_it":false}]}'
    return fake_post(model, messages, max_tokens, temperature, purpose)
llm._post = fake_scan_post
scanner._last.update(at=0.0, files=None)
found = scanner.scan(fvg, cr, "x.jpg", _dt2(2026, 10, 7, 9, 40, tzinfo=ET))
ok(found and store.scans(1)[0]["play"] == "5m DB reversal set up", "scanner logs a spotted setup")
ok(scanner.scan(fvg, cr, "x.jpg", _dt2(2026, 10, 7, 9, 41, tzinfo=ET)) is None, "scanner does not re-scan the same screenshot")
config.DAILY_BUDGET_USD = 0.000001
ok(store.over_budget() and learning.run_shadow() == 0, "budget guard pauses shadow tests")
config.DAILY_BUDGET_USD = 1.5
llm._post = fake_post
r = c.post("/screenshot?token=tok&kind=fallback", content=b"\xff\xd8x")
ok(r.json()["ok"] and store.latest_screenshot()["kind"] == "fallback", "screenshot kind stored")
st = agent.status()
ok(st["last_screenshot_kind"] == "fallback" and "spend_today_usd" in st, "status reports screenshot kind and spend")
dash = c.get("/api/dashboard?days=30").json()
ok("scans" in dash and "vision" in dash and "backtest" in dash, "dashboard API carries scans, vision, backtest")

# 11. scoring spotted setups on a price tape
t0 = 1_800_000_000_000
tape = [(t0 + i * 1000, p) for i, p in enumerate([101, 100, 99.5, 101, 102, 103, 102.5, 101, 100.2])]
ok(scanner.replay(tape, "bull", 100.0, 99.0, 103.0, t0) == (2.5, "2R + runner to 3R"), "replay: 2R + runner to target")
ok(scanner.replay(tape[:4], "bull", 100.0, 99.0, 103.0, t0)[1] == "auto-closed 2h", "replay: auto-close when the tape ends")
ok(scanner.replay([(t0, 100.5), (t0 + 1, 100.2)], "bull", 100.0, 99.0, 103.0, t0) == (0.0, "never filled"), "replay: never filled")
ok(scanner.replay([(t0, 100.0), (t0 + 1, 98.9)], "bull", 100.0, 99.0, 103.0, t0) == (-1.0, "stopped (-1R)"), "replay: stopped")
store.add_scan((_dt2.now(timezone.utc) - timedelta(hours=5)).isoformat(), "y.jpg", "MNQ1!", "5m DB continuation", "bull", "ready", 100.0, 99.0, 103.0, 0.8, ["x"], False)
class FakeTape(FVG):
    def __init__(self):
        pass
    def call(self, name, **kw):
        base = int((_dt2.now(timezone.utc).timestamp() - 5 * 3600) * 1000)
        bars = [[base + i * 1000, p] for i, p in enumerate([100, 99.8, 101, 102, 103.1])]
        bars.insert(2, [None, 50.0])          # the real tool has null timestamps
        bars.append([base + 500, 100.1])      # and out-of-order rows
        return {"symbol": kw.get("symbol"), "day": kw.get("day"), "n": len(bars), "bars": bars}
ok(FakeTape().archived_prices("MNQ1!", "2026-10-06")[0][1] == 100 and len(FakeTape().archived_prices("MNQ1!", "2026-10-06")) == 6
   and FakeTape().archived_prices("MNQ1!", "2026-10-06")[1][1] == 100.1, "archived_prices normalised: nulls dropped, sorted")
ok(scanner.score_pending(FakeTape()) == 1 and store.scored_scans()[0]["r"] == 2.5, "spotted setup scored from the archive")

# 12. management rules: a 5m DB against the play closes it on the tape
tape2 = [(t0 + i * 1000, p) for i, p in enumerate([100, 99.8, 100.5, 100.9, 101.4, 102.5, 103])]
r_m, o_m = scanner.replay(tape2, "bull", 100.0, 99.0, 103.0, t0, kills=[t0 + 3000])
ok(r_m == 0.9 and "5m DB against" in o_m, f"replay closes at the opposing 5m DB ({r_m}, {o_m})")
row_old = {"entry_id": 2, "symbol": "MNQ1!", "direction": "bull",
           "entry_at": (_dt2.now(timezone.utc) - timedelta(hours=6)).isoformat()}
class FakeEvents(FVG):
    def __init__(self):
        pass
    def mt_events(self, symbol, limit=12):
        return [{"received_at": (_dt2.now(timezone.utc) - timedelta(hours=5)).isoformat(), "tf": "5m", "text": "Lower Double Break"},
                {"received_at": (_dt2.now(timezone.utc) - timedelta(hours=7)).isoformat(), "tf": "5m", "text": "Lower Double Break"},
                {"received_at": (_dt2.now(timezone.utc) - timedelta(hours=5)).isoformat(), "tf": "1m", "text": "Lower Double Break"}]
    def call(self, name, **kw):
        base = int((_dt2.now(timezone.utc) - timedelta(hours=6)).timestamp() * 1000)
        return [[base + i * 60000, p] for i, p in enumerate([100, 99.9, 100.2, 100.6] + [101.0] * 100)]
kills = agent._kill_events(FakeEvents(), row_old)
ok(len(kills) == 1, f"kill events: only 5m DBs against the play after entry ({len(kills)})")
store.update_decision(2, entry_at=row_old["entry_at"], kill_events=kills, managed_r=None)
ok(agent.manage_pending(FakeEvents()) >= 1 and store.decisions(limit=100)[0] is not None, "managed scoring ran")
mrow = [r for r in store.decisions() if r["entry_id"] == 2][0]
ok(mrow["managed_r"] is not None and "5m DB against" in (mrow["managed_outcome"] or "") and mrow["managed_paper_r"] == round(mrow["managed_r"] * 0.5, 3),
   f"trade re-scored with the management rules ({mrow['managed_r']} {mrow['managed_outcome']})")
rep2 = learning.report(30)
ok("agent_with_management_rules" in rep2["books"] and "agent_with_daily_stop_minus2R" in rep2["books"], "report carries management and walk-away books")

# 13. two losses in the session -> code skip (§2.13); fixed ET times so the test never straddles a session block
at_fixed = _dt2(2026, 10, 6, 10, 0, tzinfo=ET).astimezone(timezone.utc)
for i, eid in enumerate((901, 902)):
    store.insert_decision({"entry_id": eid, "symbol": "MES1!", "entry_at": (at_fixed - timedelta(minutes=10 + i)).isoformat(),
                           "decision": "TAKE", "size": "full", "r": -1.0, "paper_r": -1.0})
e = mk_entry(903); e["at"] = at_fixed.isoformat(); d = json.loads(e["detail"])
fired, _ = rules_code.hard_rules(e, d, at_fixed)
ok(any("§2.13" in f and "2 losses" in f for f in fired), f"two session losses stop trading ({fired})")
ok(rules_code.session_losses(at_fixed - timedelta(hours=9)) == 0, "losses are counted per session block only")

# 14. higher-timeframe FVGs from the tape + rule 2.8
from app import htf  # noqa: E402
H = 4 * 3600_000
tape3 = []
for i, (o, h, l, c) in enumerate([(100, 101, 99, 100.5), (102, 103, 101.5, 102.5), (104, 105, 103.5, 104.5), (104, 104.2, 103.8, 104)]):
    tape3 += [(t0 + i * H + k * 60000, p) for k, p in enumerate([o, h, l, c])]
cs = htf.candles(tape3, 240)
ok(len(cs) == 4 and cs[0]["h"] == 101 and cs[0]["l"] == 99, "4H candles from ticks")
gaps = htf.fvgs_of(cs, "4h")
ok(len(gaps) == 2 and gaps[0]["dir"] == "bull" and gaps[0]["bottom"] == 101 and gaps[0]["top"] == 103.5 and not gaps[0]["filled"], f"bullish 4H FVG found ({gaps})")
ok(htf.rule_2_8("bear", 102.0, [{**gaps[0], "at_et": "x"}]) and htf.rule_2_8("bull", 102.0, [{**gaps[0], "at_et": "x"}]) is None,
   "rule 2.8: short inside a bullish 4H FVG is flagged, long is not")
ok(htf.relation(102.0, gaps)[0]["price_is"] == "inside" and "above" in htf.relation(110.0, gaps)[0]["price_is"], "price vs gap relation")

# 15. re-evaluation of code skips after a rule change + Jev on scanner setups
sc_row = [x for x in store.scans(10) if x["play"] == "5m DB reversal set up"][0]
ok(sc_row["jev_p_take"] == 0.7, f"Jev scored the scanner's forming setup ({sc_row['jev_p_take']})")
e10 = mk_entry(10); d10 = json.loads(e10["detail"]); d10["mt_cfg"] = "2DB"; e10["mt_text"] = "Lower Double Break (2DB)"; e10["detail"] = json.dumps(d10)
FAKE["entries"]["MNQ1!"].append(e10)
agent.tick(fvg)
r10 = [r for r in store.decisions() if r["entry_id"] == 10][0]
ok(r10["path"] == "code" and "2DB" in r10["hard_rule"], "2DB entry code-skipped")
store.update_decision(10, reeval=None)
ok(agent.reevaluate_skips(fvg) >= 1, "re-evaluation ran")
rv = json.loads([r for r in store.decisions() if r["entry_id"] == 10][0]["reeval"])
ok(rv.get("still_skipped", "").startswith("§2.4"), f"2DB skip still stands under current rules ({rv})")
# pretend the 2DB rule was relaxed: the entry is a plain DB now -> the model decides
d10["mt_cfg"] = "DB"; e10["mt_text"] = "Lower Double Break"; e10["detail"] = json.dumps(d10)
store.update_decision(10, reeval=None)
agent.reevaluate_skips(fvg)
rv = json.loads([r for r in store.decisions() if r["entry_id"] == 10][0]["reeval"])
ok(rv.get("decision") == "TAKE" and rv.get("jev_p_take") == 0.7 and "rules_version" in rv, f"skip re-decided by Jev + model ({rv.get('decision')})")
rep3 = learning.report(30)
ok("reevaluated_skips" in rep3 and rep3["reevaluated_skips"]["re_evaluated"] >= 1, "report carries re-evaluated skips")

# 16. reply parsing: prose + JSON + trailing braces, think blocks
ok(llm.parse_json('<think>maybe {x}</think> Here: {"a": 1, "b": {"c": 2}} and then {broken')["b"]["c"] == 2, "parse_json survives think blocks and trailing junk")
ok(llm.parse_json('```json\n{"a": [1,2]}\n```')["a"] == [1, 2], "parse_json reads fenced JSON")

# 17. outside reviewer (Hermes) queue + reviews + proposals
hc = TestClient(main.app)
q = hc.get("/api/review_queue?token=tok&reviewer=hermes").json()
ok(q and all(x["result"]["r_mechanical"] is not None for x in q) and "decision" in q[0] and "screenshots" in q[0],
   f"review queue lists settled trades as compact packets ({len(q)})")
rr = hc.post("/api/reviews?token=tok", json={"entry_id": q[0]["entry_id"], "reviewer": "hermes", "verdict": "wrong_take",
                                             "summary": "sister pair had a DB against", "exit_notes": "partial at the blue zone",
                                             "proposal": "IF the sister pair printed a 5m DB against within 30 min THEN SKIP",
                                             "proposal_title": "Sister DB against"}).json()
ok(rr["ok"] and rr["hypothesis_id"] and store.hypothesis(rr["hypothesis_id"])["source"] == "hermes", "review stored and proposal filed as a hypothesis")
ok(len(hc.get("/api/review_queue?token=tok&reviewer=hermes").json()) == len(q) - 1, "reviewed trade leaves the queue")
ok(main.reviews(5)[0]["verdict"] == "wrong_take" and hc.post("/api/reviews", json={"entry_id": 1}).status_code == 401, "reviews readable via MCP; POST needs the token")
pr = hc.post("/api/hypotheses/propose?token=tok", json={"title": "Hermes idea", "rule": "IF x THEN SKIP", "source": "hermes"}).json()
ok(pr["ok"] and store.hypothesis(pr["hypothesis_id"])["title"] == "Hermes idea", "direct proposal endpoint")
from app import prompts as _pr  # noqa: E402
ok("(hermes)" in _pr._lessons_block() and "sister pair had a DB against" in _pr._lessons_block(), "Hermes reviews feed the decision prompt")
sq = [x for x in main.review_queue("hermes", 20) if x.get("kind") == "scanner_setup"]
ok(sq and sq[0]["result"]["r_mechanical"] == 2.5, "scored scanner setups are in the review queue")
ok(hc.post("/api/reviews?token=tok", json={"scan_id": sq[0]["scan_id"], "verdict": "right_take", "summary": "zone bounce worked"}).json()["ok"]
   and not [x for x in main.review_queue("hermes", 20) if x.get("scan_id") == sq[0]["scan_id"]], "scanner setup review filed by scan_id")
ok(isinstance(main.instructor_calls(), list) and main.pending_setups() is not None, "instructor_calls and pending_setups tools")
ok(hc.get("/api/capture?token=tok").json()["paused"] is False and hc.post("/api/capture?token=tok", json={"paused": True}).json()["paused"] is True
   and agent.status()["capture_paused"] is True and TestClient(main.app).get("/api/capture").status_code == 401, "capture pause flag via API")
hc.post("/api/capture?token=tok", json={"paused": False})
before = len(main.review_queue("hermes", 50))
rr2 = hc.post("/api/reviews/reopen?token=tok&reviewer=hermes&days=3").json()
ok(rr2["ok"] and rr2["reopened"] >= 2 and len(main.review_queue("hermes", 50)) > before
   and all(not v["reviewer"].endswith("-superseded") for v in store.recent_reviews(10)), "re-open puts reviewed trades back in the queue; superseded reviews hidden")

# 18. screenshots kept for code skips and at exit; chart_question tool
d_shots = Path(TMP) / "decision_shots"
ok(any(p.name.startswith("10_") for p in d_shots.iterdir()), "screenshot kept for a code-skipped entry")
ok(any("_exit_" in p.name for p in d_shots.iterdir()), "screenshot kept at settle (exit)")
ok(main.decision_detail(2)["screenshots"]["at_decision"], "decision_detail lists the saved screenshots")
cq = main.chart_question(2, "Is there a blue zone below price on the 5m?")
ok("answer" in cq or "readability" in cq or "charts" in cq, f"chart_question answers from the saved screenshot ({list(cq)[:3]})")
ok(main.chart_question(999999, "x").get("error"), "chart_question says when no screenshot exists")

# 19. migrations cover every column the code writes (production had a reviews table without scan_id)
import sqlite3 as _sq  # noqa: E402
_old = _sq.connect(str(Path(TMP) / "old.db"))
_old.executescript("CREATE TABLE reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER, reviewer TEXT, at TEXT, verdict TEXT, summary TEXT, exit_notes TEXT, proposal TEXT, raw TEXT);")
_old.commit(); _old.close()
_prev = config.DATA_DIR
config.DATA_DIR = Path(TMP) / "olddir"; config.DATA_DIR.mkdir(exist_ok=True)
(Path(TMP) / "old.db").rename(config.DATA_DIR / "agent.db")
store.reset_for_tests()
store.add_review(1, "probe", "right_skip", "s", "e", None, {}, scan_id=None)
ok(store.reviews(1)[0]["reviewer"] == "probe", "old reviews table migrated (scan_id added) before insert")
config.DATA_DIR = _prev; store.reset_for_tests()

print("all tests passed")
server.should_exit = True
