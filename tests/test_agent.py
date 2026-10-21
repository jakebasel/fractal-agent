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


@fake.tool()
def trade_history(days: float = 14, symbol: str | None = None) -> dict:
    now = int(time.time() * 1000)
    cols = ["id", "symbol", "cascade", "dir", "sig", "mt_tf", "entry_bar", "entry", "stop", "stop_a", "target",
            "r", "outcome", "exit", "close_bar", "score_lag_h", "scoring", "session", "in_window", "nd",
            "retrace", "tap_depth", "fvg_gaps", "two_m", "signal_bar", "n_inv", "n_stages", "v_candles", "mt_seq", "exec"]

    def row(i, sym, r, scoring="on_time", cascade="2-stage", tf="1m", session="asia", age_h=1):
        bar = now - int(age_h * 3600_000)
        return [i, sym, cascade, "bull", "DB", tf, bar, 100, 99, 99, 103, r, "x", 101, bar + 60_000, 1.0,
                scoring, session, True, False, "deep", 0.3, 2, False, bar, 0, 2, 3.0, "MD", "skip"]
    rows = [row(1, "6A1!", 2.5), row(2, "6A1!", -1), row(3, "6A1!", 3, age_h=30), row(4, "ZB1!", -1),
            row(5, "ZB1!", -1, scoring="late"), row(6, "GC1!", 2, cascade="Gold Strategy"),
            row(7, "MNQ1!", 1, tf="5m", session="newyork")]
    if symbol:
        rows = [r for r in rows if r[1] == symbol]
    return {"cols": cols, "rows": rows, "n": len(rows), "note": "fake"}


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
    if "proposed ENTRY FILTER" in sysmsg:
        assert "Hard rules" in sysmsg and "course_passages" in messages[1]["content"]
        return '{"theory": "§2.6 runaway DB", "evidence_for": ["#1 -1R"], "evidence_against": [],' \
               '"win_rate_effect": "40% -> 50%", "recommendation": "adopt", "confidence": 0.6}'
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
    _call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "paper_stats", "arguments": {"days": 7}}}
    _acc = {"Accept": "application/json, text/event-stream"}
    ok(c.post("/mcp", json=_call, headers=_acc).status_code == 401, "agent MCP closed without the token")
    ok(c.post("/mcp/wrong", json=_call, headers=_acc).status_code == 401, "agent MCP closed with a wrong path token")
    r = c.post("/mcp", json=_call, headers={**_acc, "Authorization": "Bearer tok"})
    ok(r.status_code == 200 and "paper_book" in r.text, "agent MCP tool paper_stats works (bearer)")
    r = c.post("/mcp/tok", json=_call, headers=_acc)
    ok(r.status_code == 200 and "paper_book" in r.text, "agent MCP works with the path token")

# 9. new in v2: hard rules in code, news filter, Jev shadow, hypotheses + shadow tests, spend,
#    dashboard login, multi-window screenshots, strategy report
from datetime import datetime as _dt  # noqa: E402

e = mk_entry(6)
d = json.loads(e["detail"]); d["retrace"] = "none"; e["detail"] = json.dumps(d)
ok(rules_code.hard_rule(e, d, _dt.now(timezone.utc))[0].startswith("§2.6"), "code rule: DB with no retrace skipped")
NEWS["events"] = [{"title": "Retail Sales m/m", "at": _dt.now(timezone.utc) - timedelta(minutes=20)}]
e = mk_entry(7)
fired, info = rules_code.hard_rule(e, json.loads(e["detail"]), _dt.now(timezone.utc))
ok(fired and "news bracket" in fired and "min after" in fired, f"code rule: inside the news bracket ({fired})")
NEWS["events"] = [{"title": "Retail Sales m/m", "at": _dt.now(timezone.utc) + timedelta(minutes=20)}]
fired, info = rules_code.hard_rule(e, json.loads(e["detail"]), _dt.now(timezone.utc))
ok(fired is None, "code rule: 20 min BEFORE a release is not a skip (bracket is after-only)")
NEWS["events"] = [{"title": "Retail Sales m/m", "at": _dt.now(timezone.utc) - timedelta(minutes=130)}]
fired, info = rules_code.hard_rule(e, json.loads(e["detail"]), _dt.now(timezone.utc))
ok(fired is None, "code rule: 130 min after a release trades again")
_now = _dt.now(timezone.utc)
_far = _now + timedelta(hours=3)  # same ET date as now, whatever the clock says
if _far.astimezone(config.ET).date() != _now.astimezone(config.ET).date():
    _far = _now - timedelta(hours=3)
NEWS["events"] = [{"title": "Retail Sales m/m", "at": _far}]
fired, info = rules_code.hard_rule(e, json.loads(e["detail"]), _dt.now(timezone.utc))
ok(fired is None and info["today"], "code rule: same day but outside the bracket trades normally")
NEWS["events"] = [{"title": "Core PPI m/m", "at": _far}]
fired, info = rules_code.hard_rule(e, json.loads(e["detail"]), _dt.now(timezone.utc))
ok(fired and "CPI/PPI release day" in fired, f"code rule: CPI/PPI day skips a US index all day ({fired})")
e6 = mk_entry(8, sym="6E1!")
ok(rules_code.hard_rule(e6, json.loads(e6["detail"]), _dt.now(timezone.utc))[0] is None,
   "code rule: CPI/PPI day does not skip a non-US asset outside the bracket")
ok(rules_code.is_us_index("CME_MINI:MES1!") and rules_code.is_us_index("US500") and not rules_code.is_us_index("GC1!"),
   "US-related symbol check")
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
# CFD names (10/20): a 3-letter prefix made "US500"/"US30" read as "US5"/"US3" and never match
cr_cfd = {"charts": [{"symbol": "US500", "timeframe": "5m", "last_price": 7713.6, "white_lines": []},
                     {"symbol": "US30", "timeframe": "1m", "last_price": 52433.6, "white_lines": []}]}
ok("within" in scanner.sanity_check(cr_cfd, {"symbol": "US500", "entry": 7714.0})[1]
   and "within" in scanner.sanity_check(cr_cfd, {"symbol": "US30", "entry": 52430.0})[1]
   and scanner.sanity_check(cr_cfd, {"symbol": "NAS100", "entry": 29527.0})[0] == 0.0,
   "vision sanity matches CFD names exactly (US500 vs US30 vs NAS100)")
ok(config.sym_key("MNQ1!") == "MNQ" and config.sym_key("ZW!") == "ZW" and config.sym_key("US30") == "US30",
   "sym_key folds continuous-contract suffixes only")
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
ok(learning.assess_next() is False, "budget guard pauses hypothesis assessments")
_titles = {h["title"]: h for h in store.hypotheses()}
ok(all(t in _titles for t in ("Second play same asset reduced", "DB keeps the retracement requirement",
                              "DB fails only with a reversal zone", "London obligation with own NY setup"))
   and _titles["DB fails only with a reversal zone"]["source"] == "instructor-conflict",
   "the 4 instructor-vs-rulebook conflicts are tracked as hypotheses")
from app import prompts  # noqa: E402
_rows = [r for r in store.decisions(limit=50) if r["decision"] in ("TAKE", "SKIP")]
ok("earlier_entries_same_symbol_same_session" in json.loads(prompts.shadow_user(_rows[0], [])),
   "shadow test sees earlier same-session entries on the symbol")
_h = store.hypotheses("testing")[0]
_a = learning.assess(_h)
ok(_a["recommendation"] == "adopt" and learning.hypothesis_result(_h)["assessment"]["theory"].startswith("§2.6"),
   "hypothesis gets a written theory + evidence case")
ok(not learning._assess_due(_h, learning.hypothesis_result(_h)), "case is not redone until new changed trades or 24h")
ok("collecting data" not in learning.hypothesis_result(_h)["verdict"], "no fixed trade count before a verdict")
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

# Anthropic request shape (2026-10-13): effort set, no thinking/temperature field, the rulebook
# part of the system prompt carries one cache breakpoint, max_tokens leaves room for thinking,
# cache tokens are priced into the spend log, and an all-thinking reply is a clear error
import httpx as _httpx
_sent = {}
class _FakeResp:
    status_code = 200
    def __init__(self, data): self._d = data
    def json(self): return self._d
def _fake_httpx_post(url, json=None, timeout=None, headers=None):
    _sent.update(json)
    return _FakeResp({"model": "claude-haiku-5-5", "stop_reason": "end_turn",
                      "usage": {"input_tokens": 1000, "output_tokens": 100,
                                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 20000},
                      "content": [{"type": "text", "text": '{"ok": true}'}]})
_real_post, _real_key, _real_cache = _httpx.post, config.ANTHROPIC_API_KEY, config.ANTHROPIC_CACHE
_httpx.post, config.ANTHROPIC_API_KEY, config.ANTHROPIC_CACHE = _fake_httpx_post, "sk-test", True
try:
    big_rules = "R" * 9000 + "\n=== LESSONS FROM PAST PAPER TRADES ===\n- lesson one"
    out = llm._post_anthropic("claude-haiku-5-5", [{"role": "system", "content": big_rules},
                                                   {"role": "user", "content": "setup"}], 16000, 0.1, "decision")
    ok(out == '{"ok": true}', "anthropic call returns the text")
    ok(_sent["output_config"] == {"effort": config.ANTHROPIC_EFFORT} and "thinking" not in _sent
       and "temperature" not in _sent, "anthropic body: effort set, no thinking/temperature field")
    ok(_sent["max_tokens"] == 16000 and config.DECISION_MAX_TOKENS >= 16000, "max_tokens leaves room for thinking")
    sysb = _sent["system"]
    ok(isinstance(sysb, list) and sysb[0].get("cache_control") == {"type": "ephemeral"}
       and sysb[0]["text"].startswith("RRRR") and "LESSONS" not in sysb[0]["text"]
       and "LESSONS" in sysb[1]["text"], "rulebook part of the system prompt is the cache breakpoint; lessons stay outside it")
    last = store.db().execute("SELECT * FROM api_calls ORDER BY id DESC LIMIT 1").fetchone()
    want = (1000 * 0.10 + 20000 * 0.10 * 0.10 + 100 * 0.50) / 1_000_000
    ok(last["model"] == "claude-haiku-5-5" and abs(last["cost"] - want) < 1e-9 and last["in_tokens"] == 21000,
       "spend log prices Haiku at list price and cache reads at 10%")
    def _thinking_only(url, json=None, timeout=None, headers=None):
        return _FakeResp({"model": "claude-haiku-5-5", "stop_reason": "max_tokens",
                          "usage": {"input_tokens": 1000, "output_tokens": 4000}, "content": []})
    _httpx.post = _thinking_only
    try:
        llm._post_anthropic("claude-haiku-5-5", [{"role": "user", "content": "x"}], 4000, 0.1, "decision")
        ok(False, "empty reply raises")
    except llm.LLMError as e:
        ok("thinking" in str(e) and "DECISION_MAX_TOKENS" in str(e), "an all-thinking reply names the fix")
    ok(llm._effort(config.HEAVY_MODEL) == config.HEAVY_EFFORT and llm._effort("claude-haiku-5-5") == config.ANTHROPIC_EFFORT,
       "heavy model gets its own effort")
finally:
    _httpx.post, config.ANTHROPIC_API_KEY, config.ANTHROPIC_CACHE = _real_post, _real_key, _real_cache

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

# 20. per-symbol core book: fvg-mcp trade_history mirrored and reported per symbol
from app import symbols  # noqa: E402
n = symbols.sync(FVG())
ok(n == 6, f"trade_history mirrored, Gold Strategy row dropped ({n} rows)")
rep = symbols.report(7)
by = {x["symbol"]: x for x in rep["symbols"]}
ok(rep["symbols"][0]["symbol"] == "6A1!" and by["6A1!"]["window"]["n"] == 3 and by["6A1!"]["window"]["total_r"] == 4.5,
   "6A1! leads the symbol table with 3 trades, +4.5R")
ok(by["ZB1!"]["window"]["n"] == 1 and by["ZB1!"]["excluded"] == 1, "late-scored row excluded from ZB1!")
ok("GC1!" not in by and rep["all"]["n"] == 5, "Gold Strategy rows are not part of the core book")
ok(by["MNQ1!"]["by_tf"]["5m"]["n"] == 1 and by["MNQ1!"]["by_session"]["newyork"]["n"] == 1, "by-timeframe and by-session splits")
ok(abs(sum(by["6A1!"]["by_day"].values()) - 4.5) < 1e-9 and len(rep["days"]) == 7, "per-day totals add up over the 7 day columns")
ok(symbols.sync_if_due(FVG()) == 0, "sync is rate-limited between ticks")
ok(main.symbol_stats(7)["all"]["n"] == 5, "symbol_stats MCP tool")
sc = TestClient(main.app)
ok(sc.get("/api/symbols").status_code == 401, "/api/symbols is closed without login")
sc.post("/login", data={"password": "pw"}, follow_redirects=False)
ok(sc.get("/api/symbols?days=7").json()["all"]["n"] == 5, "/api/symbols serves the report after login")
ok(sc.get("/api/dashboard?days=7").json()["symbols"]["all"]["n"] == 5, "dashboard payload carries the symbol table")

# 21. Telegram Q&A: secret-checked webhook, one chat only, Claude tool loop over the read-only tools
from app import telegram_bot  # noqa: E402
SENT, LLM_TURNS = [], []
config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID = "123:abc", "42"
telegram_bot._api = lambda method, **p: SENT.append((method, p)) or {"ok": True}


def fake_chat(model, system, messages, tools, max_tokens, effort, purpose):
    LLM_TURNS.append({"model": model, "tools": [t["name"] for t in tools], "messages": list(messages)})
    if len(LLM_TURNS) == 1:
        return {"stop_reason": "tool_use", "content": [
            {"type": "tool_use", "id": "t1", "name": "symbol_stats", "input": {"days": 7}}]}
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "6A1! pays most: n=3, +4.5R."}]}


llm.chat_with_tools = fake_chat
tc = TestClient(main.app)
upd = {"update_id": 1, "message": {"chat": {"id": 42}, "text": "which symbol pays?"}}
ok(tc.post("/telegram", json=upd).status_code == 401, "telegram webhook rejects a missing secret")
ok(tc.post("/telegram", json={**upd, "update_id": 2, "message": {"chat": {"id": 7}, "text": "hi"}},
           headers={"X-Telegram-Bot-Api-Secret-Token": telegram_bot.secret()}).status_code == 200
   and not SENT, "telegram ignores other chats")
telegram_bot.handle(42, "which symbol pays?")
ok(LLM_TURNS[0]["model"] == config.TELEGRAM_MODEL and "symbol_stats" in LLM_TURNS[0]["tools"]
   and "chart_question" in LLM_TURNS[0]["tools"], "telegram uses the Telegram model with the read-only tools")
_res = LLM_TURNS[1]["messages"][-1]["content"][0]
ok(_res["type"] == "tool_result" and json.loads(_res["content"])["all"]["n"] == 5, "tool result fed back to the model")
ok(SENT[-1] == ("sendMessage", {"chat_id": 42, "text": "6A1! pays most: n=3, +4.5R.", "disable_web_page_preview": True}),
   "answer sent to the chat")
ok(len(store.kv_get("tg_history:42")) == 2, "conversation kept for follow-ups")
telegram_bot.handle(42, "/reset")
ok(store.kv_get("tg_history:42") == [] and SENT[-1][1]["text"] == "Conversation cleared.", "/reset clears it")
_names = [t["name"] for t in telegram_bot.tool_defs()]
ok("fvg_entries" in _names and "fvg_setups" in _names, f"fvg-mcp tools offered with the fvg_ prefix ({len(_names)} tools)")
ok(isinstance(json.loads(telegram_bot.run_tool("fvg_entries", {"symbol": "MNQ1!", "limit": 2})), list),
   "fvg_ tool call goes to fvg-mcp")
ok("rulebook.md ---" in telegram_bot.system_prompt() and "Hard rules" in telegram_bot.system_prompt(),
   "rulebook is in the Telegram system prompt")
LLM_TURNS.clear()
telegram_bot._download = lambda fid: b"\x89PNG fake"
telegram_bot.handle(42, "", image_id="photo1")
_q = LLM_TURNS[0]["messages"][-1]["content"]
ok(_q[0]["type"] == "image" and _q[0]["source"]["media_type"] == "image/png" and "Analyse" in _q[1]["text"],
   "screenshot goes to the model as an image with a default question")
ok(config.TELEGRAM_MODEL == "claude-haiku-5-5", "Telegram defaults to Haiku")
LLM_TURNS.clear()
telegram_bot.handle(42, "/deep why do 2DBs fail?")
ok(LLM_TURNS[0]["model"] == config.TELEGRAM_DEEP_MODEL and LLM_TURNS[0]["messages"][-1]["content"] == "why do 2DBs fail?",
   "/deep sends one question to the stronger model")
telegram_bot.handle(42, "/model opus")
LLM_TURNS.clear()
telegram_bot.handle(42, "and now?")
ok(LLM_TURNS[0]["model"] == "claude-opus-5-5", "/model changes the default")
telegram_bot.handle(42, "/model haiku")
LLM_TURNS.clear()
telegram_bot.handle(42, "/model opus what beats what on US500?")
ok(LLM_TURNS[0]["model"] == "claude-opus-5-5" and LLM_TURNS[0]["messages"][-1]["content"] == "what beats what on US500?"
   and telegram_bot.default_model() == "claude-haiku-5-5", "/model <name> <question> uses it for that question only")
ok(main.trade_breakdown("6A1!", 7)["all"]["n"] == 3 and main.trade_breakdown(None, 7)["worst_buckets"] is not None,
   "trade_breakdown splits winners vs losers per symbol")
ok(telegram_bot._image_file_id({"photo": [{"file_id": "s", "file_size": 10}, {"file_id": "b", "file_size": 99}]}) == "b",
   "largest photo size is used")

# 21b. Zoom Trade Alerts relay: Zoom messages queue for the Mac instead of reaching the model
ok(telegram_bot.is_zoom_message("https://us06web.zoom.us/j/123?pwd=x")
   and telegram_bot.is_zoom_message("/stop") and telegram_bot.is_zoom_message("/last 5")
   and not telegram_bot.is_zoom_message("which symbol pays?")
   and not telegram_bot.is_zoom_message("https://www.tradingview.com/x/abc"),
   "Zoom links and Zoom commands route to the Mac; questions and other links don't")
store.kv_set("zoom_last_poll", time.time())
SENT.clear()
LLM_TURNS.clear()
telegram_bot.zoom_enqueue({"chat": {"id": 42}, "text": "/join"})
ok(telegram_bot.is_zoom_message("https://meet.google.com/abc-def"), "the link after a bare /join goes to the Mac")
telegram_bot.zoom_enqueue({"chat": {"id": 42}, "text": "https://meet.google.com/abc-def"})
ok(not telegram_bot.is_zoom_message("https://www.tradingview.com/x/abc"), "only ONE follow-up link is taken")
ok(not SENT and not LLM_TURNS, "queued Zoom messages never reach the model or reply while the Mac is up")
ok(tc.get("/zoom/inbox").status_code == 401, "zoom inbox rejects a missing token")
_inbox = tc.get("/zoom/inbox?after=0", headers={"X-Zoom-Token": telegram_bot.zoom_token()}).json()
ok([i["message"]["text"] for i in _inbox["items"]][-2:] == ["/join", "https://meet.google.com/abc-def"],
   "zoom inbox returns queued messages in order")
ok(tc.get(f"/zoom/inbox?after={_inbox['seq']}", headers={"X-Zoom-Token": telegram_bot.zoom_token()}).json()["items"] == [],
   "zoom inbox returns nothing past the cursor")
store.kv_set("zoom_last_poll", 0)
telegram_bot.zoom_enqueue({"chat": {"id": 42}, "text": "/status"})
ok(SENT and "isn't running on the Mac" in SENT[-1][1]["text"], "warns when the Mac app isn't polling")
config.TELEGRAM_BOT_TOKEN = config.TELEGRAM_CHAT_ID = ""

# 22. Reference library: one searchable store of course, live sessions, digests, lessons, reviews
from app import library  # noqa: E402
_session = ("[10:04:06] Okay so when I'm looking at the purple zone in Asia, I want price to sweep it first.\n"
            "[10:05:10] If the double break prints after the sweep, that is the DB continuation I take.\n" * 6)
_id, _new = library.add_document("live_session", "test:s1", "Live 10/14 AM", "2026-10-14T14:00:00", _session)
ok(_new and not library.add_document("live_session", "test:s1", "Live 10/14 AM", "2026-10-14T14:00:00", _session)[1],
   "library stores a session once (same text = no re-index)")
_hits = library.search("purple zone sweep", k=3, kind="live_session", since="2026-10-01")
ok(_hits and _hits[0]["source"] == "test:s1" and "[10:04:06]" in _hits[0]["text"] and _hits[0]["at"].startswith("2026-10-14"),
   "library search finds the session, keeps the timestamp and the date")
ok(library.search("db", k=3) and library.search("DB'; DROP TABLE x --", k=3) is not None,
   "trading shorthand expands (DB -> double break) and punctuation can't break the query")
ok(not library.search("purple zone", k=3, kind="course") or all(h["kind"] == "course" for h in library.search("purple zone", k=3, kind="course")),
   "kind filter narrows results")
_n_sync = library.sync_internal()
ok(_n_sync > 0 and library.count().get("course", 0) > 0, f"course files and lessons sync into the library ({library.count()})")
_orig_post = llm._post


def _digest_post(model, messages, max_tokens=1500, temperature=0.1, purpose="other"):
    if purpose == "library_digest":
        assert model == config.LIBRARY_DIGEST_MODEL and "RULEBOOK" in messages[0]["content"]
        return json.dumps({"title": "Asia purple sweep then DB", "summary": "He traded the Asia sweep.",
                           "topics": ["purple zone", "DB"], "trade_calls": [{"time": "10:05", "instrument": "NAS",
                           "side": "long", "what": "DB continuation after sweep", "outcome": "+3R"}],
                           "teachings": [{"time": "10:04", "point": "sweep the purple zone first"}],
                           "rule_proposals": [{"title": "Sweep before DB", "rule": "IF Asia purple swept THEN TAKE DB",
                                               "quote": "I want price to sweep it first", "time": "10:04"}]})
    return _orig_post(model, messages, max_tokens, temperature, purpose)


llm._post = _digest_post
_h_before = len(store.hypotheses(["testing", "queued", "approved", "rejected"]))
_res = library.ingest_session("test:s2", "Live 10/14 PM", "2026-10-14T20:43:00", _session + "[20:50:00] new part\n")
ok(_res["digest"] and _res["digest"]["title"] == "Asia purple sweep then DB", "a new session gets a digest")
ok(library.search("sweep the purple zone first", kind="digest", k=2), "the digest itself is searchable")
ok(len(store.hypotheses(["testing", "queued", "approved", "rejected"])) >= _h_before, "rule proposals filed (or matched) as hypotheses")
ok(main.session_digests(days=3650)[0]["trade_calls"][0]["outcome"] == "+3R", "session_digests MCP tool returns the calls")
llm._post = _orig_post
_lc = TestClient(main.app)
ok(_lc.post("/library/ingest?title=x", content=b"x" * 500).status_code == 401, "library ingest needs the agent token")
ok(_lc.post("/library/ingest?title=x", content=b"short", headers={"X-Agent-Token": "tok"}).status_code == 400,
   "library ingest rejects near-empty transcripts (test runs)")
ok(_lc.get("/library/search?q=purple+zone", headers={"X-Agent-Token": "tok"}).json()["hits"],
   "library search endpoint answers with the token")
ok(any(h.get("kind") for h in main.knowledge_search("purple zone sweep")), "knowledge_search (Telegram/Claude/Hermes) reads the library")
_cn = main.chart_now("is there a reversal zone on US30?")
ok("error" not in _cn and _cn.get("images", 0) >= 1 and "screenshot_age_s" in _cn,
   f"chart_now reads the newest live screenshot set ({ {k: _cn.get(k) for k in ('images', 'error')} })")
ok("chart_now" in [t["name"] for t in telegram_bot.tool_defs()] and "NEW gap in" in telegram_bot.system_prompt().replace("\n", " ")
   or "NEW gap" in telegram_bot.system_prompt(), "Telegram has chart_now and the DB-after-retracement rule")

print("all tests passed")
server.should_exit = True
