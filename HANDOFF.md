# Fractal Agent — handoff (start here in Claude Code)

Written 2026-10-07 ~1 AM ET at the end of the first build session (claude.ai chat, cloud
workspace). That workspace could NOT reach motivationpro.tech, so nothing here has run against
the live server yet. Everything passes against a fake fvg-mcp and a fake LLM
(`tests/test_agent.py`).

## What this is

A **paper-only** AI review layer on top of the existing rules engine (`jakebasel/fvg-mcp`).

```
TradingView alerts ──► fvg-mcp (rules engine, scores every entry)
                              │  read-only MCP  (https://fvg.motivationpro.tech/mcp)
                              ▼
VPS screenshot ──► fractal-agent ──► OpenRouter: cheap vision model reads the chart
 (every 30s)        (this repo)        DeepSeek decides TAKE/SKIP + writes lessons
                              │
                              ▼
               SQLite /data/agent.db + /data/trades.csv
               read-only MCP at /mcp  → ask Claude "how did today's paper trades go?"
```

1. Every 15s it asks fvg-mcp for new entries on **MNQ1! and MES1!** (`entries` tool). fvg-mcp
   has already done the mechanical part: MT signal armed it, FVG cascade 5m→1m→30s (or 1m→30s)
   completed, close over the series. Entry, stop and 1:3 target come from fvg-mcp.
2. Code-level hard rules first (no AI call): ND/trend-fallback, outside window, NY after
   11:00 ET, weekend.
3. The latest VPS screenshot (if < 3 min old) goes to the **vision model** once; it returns a
   JSON read of what the alerts don't carry: white M/2M/DB/2DB lines and whether a body closed
   through them, reversal zones, purple/blue zones, NDOG, Spotlight, EMAs, trend table.
4. **DeepSeek** gets: the rulebook (`rules/`), the latest lessons, fvg-mcp's entry detail,
   both indices' setups and recent MT signals (divergence), and the chart read. Returns
   TAKE/SKIP, grade (A+/A/B/C), size (full/reduced), reasons citing rule sections.
5. When fvg-mcp scores the entry (`f_pnl_r`), the row is settled. `r` = result as if taken at
   full size, `paper_r` = r × size (reduced = 0.5) for TAKEs, 0 for SKIPs. Skips keep their
   counterfactual `r`, so we can measure whether the filter adds anything.
6. DeepSeek writes a lesson per settled trade (right/wrong take/skip, lesson, rule ref, optional
   rule-change proposal). The last 20 lessons go back into every decision prompt. **Proposals
   never change rules on their own** — Jake approves, then they go in `rules/amendments.md`.

7. **Learning loop** (`app/learning.py`, added 2026-10-07). Every proposal becomes a
   *hypothesis* (duplicates merge and count as support). Up to 8 are "testing" at once: each
   reviewed setup, past (60-day backfill) and future, gets a shadow decision per hypothesis
   (one DeepSeek call covers all of them). When trades settle, each hypothesis' book is
   compared with the agent's and the core strategy's **on the same trades**. Jake approves or
   rejects on the dashboard; approved ones are then committed to `rules/amendments.md`. Every
   decision records `rules_version` (hash of rules/) so results can be split per rulebook.
8. **Jev** (TypeSafe System One, via OpenRouter `/systemone`, `app/jev.py`): one ~100 ms call
   per setup scores a **playbook generated from rules/** (judgment hard rules, every must-have,
   booster and downgrade, amendment compliance, play kind, grade, P(TAKE)); approving an
   amendment changes Jev's questions on the next call. Runs on engine setups (shadow next to
   DeepSeek, or `gate`), on the scanner's forming setups, and on skips re-evaluated after a
   rule change (`agent.reevaluate_skips`: code skips from the last 3 days are re-decided under
   the current rules; the original decision is kept, the re-evaluation sits next to it).
   Switch to gate once the Breakdown tab shows Jev agreeing with the agent.
9. Code hard rules: 2DB, ND, §2.2 news (ForexFactory calendar, red-folder USD releases only,
   from the release to 2 h after it, nothing before; `NEWS_BEFORE_MIN`=0/`NEWS_AFTER_MIN`=120), DB with
   retrace `none`/`shallow`, two losses this session, weekend, NY/London/Asia windows, long
   inside a bearish 4H FVG (from the price archive). `app/rules_code.py`, `app/htf.py`.
10a. **Per-symbol core book** (`app/symbols.py`, added 2026-10-08). Every 10 min the agent mirrors
    fvg-mcp's `trade_history` (every scored cascade entry on every symbol it gets alerts for, full
    size, no AI filter) into `core_trades` (first run backfills 30 days). Dashboard tab **Symbols**,
    `/api/symbols?days=`, MCP tool `symbol_stats(days)`: per symbol n, win%, avg R, total R, max DD,
    today, total R per ET day for the last 7 days, by timeframe and session. Only on_time/rescored/
    fact scoring counts; Gold Strategy rows are dropped. Jake's question: which instruments does the
    core strategy pay on? Env: `SYMBOLS_SYNC_S` (600), `SYMBOLS_BACKFILL_DAYS` (30).
10. Dashboard at `/` (password: `DASHBOARD_PASSWORD`, 30-day cookie): status, cumulative R
    agent vs core, live screen, setups feed with the screenshots each decision used, learning
    tab with approve/reject, breakdowns by play/session/config/grade/booster/hard rule, spend
    by purpose/model/day, rulebook versions. `app/dashboard.html`, data from `/api/dashboard`.

There is no order-placement code in this repo. Keep it that way until Jake says otherwise.

## Rules and course material

- `knowledge/` — the full course: 9 course transcripts, the mini lessons, the Reversal Set Up
  video, the SOP and strategy PDFs as text. `app/knowledge.py` searches it (BM25) and puts the
  6 most relevant passages into every decision prompt, so DeepSeek can quote the instructor.
  See `knowledge/README.md` for what's in it and how to add more.
- `rules/rulebook.md` — compiled rulebook: definitions, 12 hard rules, grading, management,
  the Reversal Set Up model (newest video), what can't be seen.
- `rules/live_rules.md` — rules from the 12 live sessions.
- `rules/amendments.md` — Jake-approved changes; highest priority.
- Rules are re-read on every call: editing them takes effect on the next decision (but a
  container redeploy resets files to what's in git, so commit changes).
- Live sessions from Oct 2026 on come from Jake's Wispr Flow recordings. Run `/live-session` in
  Claude Code after a session: it pulls new finalized recordings through the Wispr Flow connector,
  files the instructor's transcript in `knowledge/lessons/`, labels his calls for the
  `instructor_calls` tool and adds new rules to `rules/live_rules.md`. `knowledge/wispr_ingested.json`
  is the ledger. The VPS agent cannot reach Wispr Flow itself.
- Source material lives in the claude.ai "Trading" project (course transcripts, live session
  transcripts, `Chart Analysis Playbook.md`, `Reversal Set Up (transcript).txt`).

## Deploy (Coolify on the Hostinger VPS)

Not deployed yet. Steps:

1. Coolify → Projects → **New Project** "fractal-agent" → Add resource → Public/Private
   GitHub repo `jakebasel/fractal-agent`, branch `main`, build pack **Dockerfile**, port 8080.
2. Domain: `https://agent.motivationpro.tech` (add the DNS A record like the other apps).
3. **Persistent storage**: mount a volume at `/data` (SQLite, CSV, screenshots). Without it
   every deploy wipes the log.
4. Environment variables:
   - `OPENROUTER_API_KEY` — Jake's key (currently on the fvg-mcp app; copy it, or make it a
     Coolify Shared Variable and reference it from both apps).
   - `AGENT_TOKEN` — any long random string; protects `/screenshot` and `/log.csv`. The same
     value goes on the tv-capture app.
   - `DASHBOARD_PASSWORD` — login for the dashboard at `/`.
   - Optional: `JEV_MODE` (shadow | gate | off), `NEWS_FILTER` (1), `MAX_TESTING_HYPOTHESES` (8),
     `MIN_N_FOR_VERDICT` (30).
   - Optional: `DECISION_MODEL` (default `deepseek/deepseek-chat`), `VISION_MODEL` (default
     `google/gemini-2.5-flash`), `SYMBOLS` (default `MNQ1!,MES1!`), `POLL_SECONDS` (15),
     `FVG_MCP_URL` (default public URL; inside Coolify the internal container URL is faster).
   - Check both model ids exist on OpenRouter before the first session; swap if renamed.
5. Deploy, then `curl https://agent.motivationpro.tech/health` → `key_set: true`, `loops` rising.
6. Add `https://agent.motivationpro.tech/mcp` as a custom connector in claude.ai so Claude can
   call `paper_stats`, `decisions`, `decision_detail`, `lessons`, `agent_status`.

## VPS screenshot capturer (tv-capture/)

Coolify app `tv-capture` (same project, base directory `/tv-capture`, volume `/data`, domain
https://tv.motivationpro.tech). Headless Chromium logged into TradingView with Jake's session
cookies screenshots the pages in `TV_PAGES` every 30 s during futures hours and posts them to
`/screenshot` with `kind=vps` and `layout=<TV_LAYOUT>`; the agent stores that layout text per
kind and the vision prompt uses it; the agent reads whichever set is newest. (The Mac
screenshot uploader was removed 2026-10-08: it stopped whenever the screen locked.) Env: `AGENT_URL`, `AGENT_TOKEN`, `UI_PASSWORD`
(dashboard password), `TV_PAGES` (one 4-chart layout URL, or one URL per chart), `TV_LAYOUT`
(describe what the images show, in order). Login: open the app's page, enter the password and
the `sessionid` + `sessionid_sign` cookies from Chrome (DevTools → Application → Cookies →
tradingview.com). They persist on the volume. When the session expires the agent dashboard
shows "VPS capture is logged out" and `/health` on the capture app shows `logged_in: false`:
paste fresh cookies. Memory: headless Chromium needs about 1 GB; the app has a 1.5 GB limit.

## Querying the log

- Claude (after adding the connector): "paper_stats for the last 7 days", "show today's
  decisions", "what lessons have come up".
- CSV: `https://agent.motivationpro.tech/log.csv?token=AGENT_TOKEN`
- JSON: `/stats`, `/decisions?limit=50`, `/lessons` (same token).

## Tests

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tests/test_agent.py
```
Spins up a real FastMCP server as a fake fvg-mcp and stubs the LLM. Checks: MCP round-trip,
no review of pre-start history, vision read, B grade → reduced size, ND skipped by code with no
model call, stale → MISSED, Gold Strategy ignored, settlement maths, lesson stored, CSV in ET,
stats, token gate, screenshot upload, the agent's own MCP tool.

## Next steps (in order)

Done 2026-10-07: deployed on Coolify (project fractal-agent), VPS capture, dashboard,
learning loop, Jev shadow scoring, news filter, spend tracking. Still open:

1. ~~Deploy + screenshot capture (above).~~ Watch one session; check `decision_detail` rows to see what
   the vision model actually read off the screen. Tune `VISION_PROMPT` in `app/prompts.py`
   until it reliably reads white lines and reversal zones. This is the weakest link.
   Reference chart images are in `knowledge/reference/images/`; sending one or two with each
   vision call as examples of what the markers look like should improve the read.
2. Confirm fvg-mcp's `entries` rows for MNQ1!/MES1! carry `f_pnl_r` within ~2h (they did on
   2026-10-05). `scoring_health` on fvg-mcp shows whether scoring is on time.
3. ~~News filter~~ done (`rules_code.news_rule`). Check the dashboard's "Hard rules" table
   after a few weeks: if §2.2 skips would have been profitable, loosen it via a hypothesis.
4. Higher-timeframe context: 4H/daily FVGs are usually off-screen. Options: a third
   screenshot of a 4H chart, or compute them from fvg-mcp's archived prices.
5. Weekly report: compare TAKE vs SKIP vs all engine entries per setup type/session; collect
   lesson proposals for Jake to approve into `amendments.md`.
6. Only after weeks of paper data: discuss live execution (fvg-mcp already has PickMyTrade
   plumbing with dry-run). Not before.

## Facts worth knowing

- fvg-mcp repo rules (its CLAUDE.md): push to `main` = production deploy of the system Jake
  trades on; all 11 tests must pass first; times shown to humans are ET; its MCP is read-only.
- MT alerts on MNQ1!/MES1! currently run Market Translator [17-09-26] (1m/5m). Two disabled
  alerts on MET1! use [23-09-26], the version with reversal lines — recreating MNQ/MES alerts on
  23-09-26 might expose reversal events in the alert text (untested).
- 2026-10-07: TradingView alerts were still posting to the old Railway URL after the VPS move;
  Jake repointed MNQ/MES/MYM to `https://fvg.motivationpro.tech/webhook?token=…`. Data resumed 00:49 ET.
  2026-10-08: the other 29 active Market Translator alerts were still on the Railway URL (fvg-mcp had
  heard from only MNQ/MES/MYM since 10-06); all repointed via TradingView's own alerts API from a
  logged-in Chrome tab (`pricealerts.tradingview.com/list_alerts` + `modify_restart_alert`, payload
  shape in git history of this note). Each MT webhook URL carries `token`, `source=market_translator`,
  `symbol=<lowercase, e.g. mnq1>` and `tf=1m|5m`: fvg-mcp labels the event from those params, so a
  bare URL (ES/NQ/YM had one) or a wrong symbol (HG1! 1m said ng1) silently loses or mislabels data.
  Both fixed. The two disabled MET1! [23-09-26] test alerts still point at Railway (left alone).
- 2026-10-08: Market Translator [24-09-26] 1m + 5m alerts exist for EVERY product TradingView's
  symbol-search "Tradovate" filter lists (114 roots; Jake: "I can still trade them, just not with
  Apex, so we should track them"). Two groups in the Primary watchlist: `###OTHER` = the 24 roots
  Apex Trader Funding / Lucid Trading allow beyond the original set (Apex Tradovate list at
  apextraderfunding.com/help-center/tradovate/tradovate-commission-instruments/, Lucid at
  support.lucidtrading.com article 11508978), `###OTHER-TRADOVATE` = the other 71 (Eurex, Coinbase
  Derivatives dated contracts, treasuries, yields, nanos, single-stock futures, mini grains, full
  BTC/ETH ...). Created by cloning the MES1! alerts via `pricealerts.tradingview.com/create_alert`
  (same payload as modify minus alert_id; CBOT grains only accept the plain `EXCHANGE:SYM1!` symbol
  string). MT webhook URL `symbol=` param: `mnq1`-style for roots in fvg-mcp's `_CONT_ROOTS`, the
  exact FVG spelling (`ho1!`, `golz2026`) for everything else, or fvg-mcp files the MT signal under
  a different key than the FVG data ("has a Market Translator signal but NO fair value gap data").
  Known dead (study_error, the Pine script cannot run there): MET 5m, and on the first pass ZO/ZR/
  ZT/6M 5m, FSXE/FVS 1m. The Ironbeam filter is NOT usable the same way: it lists ~8,900 futures
  (every exchange TradingView carries, spreads included); Jake picks a curated set.
- 2026-10-08: relay alerts `FVG Relay v1.02 #2` .. `#7` on CME_MINI:MNQ1! 30S, same webhook, 20
  symbol slots each (inputs in_3, in_5 ... in_41 with enable bools in_2 ... in_40): #2/#3 = the 29
  Apex/Lucid roots, #4-#7 = the 71 OTHER-TRADOVATE symbols. Relay #1 (the original) is a
  WATCHLIST alert, so it fires once per watchlist symbol per 30s bar (now 128x the same 20-symbol
  batch) and fvg-mcp answers "request took too long" on some; recreating it on a single symbol
  would cut that. The FVG v16.60 watchlist alert tracks Primary dynamically, so every watchlist
  symbol gets FVG events; the symbol throttle ("temporarily limited due to frequent triggers")
  is the risk.
- (superseded) two more relay alerts, `FVG Relay v1.02 #2` (6A 6B 6C 6E 6J 6S 6N PL PA RB HO QM QG
  MCL MGC SIL ZS ZC ZW ZL) and `#3` (ZM HE LE GF EMD NKD M2K M6A M6E), on CME_MINI:MNQ1! 30S, same
  webhook: the relay script has 20 symbol slots (inputs in_3, in_5 ... in_41 with enable bools in
  in_2 ... in_40). Relay #1 is a WATCHLIST alert, so it fires once per watchlist symbol per 30s bar
  (49x the same 20-symbol batch) and fvg-mcp sometimes answers "request took too long"; recreating
  it on a single symbol would cut that 49x. The FVG v16.60 watchlist alert tracks Primary
  dynamically (symbolset_data shows all 49), so the 24 new symbols already get FVG events.
- 2026-10-08 (later): `###OTHER-IRONBEAM` section on Primary: 30 liquid roots TradingView's
  Ironbeam filter lists that Tradovate does not (CBOE VX VXM; ICE US DX KC CC SB CT OJ RS MME MFS;
  ICE Europe BRN G C W RC Z; CBOT ZQ KE MZW MZS MZC; CME SR3 NIY 6Z XRP LBR DC CNH; COMEX ALI),
  MT 1m+5m each. The Ironbeam filter itself returns ~8,900 futures (every exchange, spreads
  included): this is a curated cut, not "all of Ironbeam". Jake's data plan has NO permission
  for CBOE / ICE symbols inside the relay script (`no_permissions_for_symbol_used_in_input`), so
  relay #8 = ZQ KE MZW only and relay #9 = MZS MZC SR3 NIY 6Z XRP LBR DC CNH ALI; the 17 CBOE/ICE
  symbols have MT alerts and FVG-watchlist coverage but no relay price feed. study_error (dead):
  OJ 1m+5m, ALI 1m, CNH 1m.
- 2026-10-08: relay #1 recreated as a single-symbol alert (`FVG Relay v1.02 #1`, id 5802648868, on
  CME_MINI:MNQ1! 30S, same 20 symbols); the old watchlist relay (5370548697) refused to delete
  via the connector ("internal") -- stop it / delete it from the Alerts panel if it still posts.
- fvg-mcp 2026-10-08: `/analysis` page (sortable headers, filter panel, top scrollbar, 1m/5m and
  M/DB cells with win% + avg R, Symbol page `#sym=` with 100-row pages and TradingView layout
  links; `/api/analysis`, `/api/analysis/trades`). Dashboard lag: `/api/entries` and `/api/setups`
  rebuild in 20-35 s with ~150 symbols and were cached 2 s, so a poll after expiry waited the whole
  rebuild. Now stale-while-revalidate (`_swr_rebuild`): a stale cache is served at once and rebuilt
  single-flight in the background; TTLs ENTRIES_TTL_S=20 / SETUPS_TTL_S=10. The board is therefore
  up to ~60 s behind. The next step, if that matters, is making the rebuilds cheaper (profile
  `_entries_payload`'s price-stream sims and `compute_setups` per symbol).
- fvg-mcp 2026-10-08 (evening): Jake's signal-priority rule is enforced at entry time. A leg that
  would `enter` is voided (`status: superseded`, `void_reason`) when a newer Market Translator
  signal on the SAME timeframe arrived between the arming signal and the entry trigger (arrival
  times, not bar labels); the only exception is an opposite M in the same session (2M). The
  research rows carry `overridden` / `overridden_by` computed the same way over the compiled
  history, and the Analysis ranking, Symbol tiles and stats exclude those rows (listed greyed).
  Signal expiry stays at whatever Settings says (Jake wants it OFF = 0; set in Settings). No cap
  on entries per arm (Jake: every entry that meets the parameters counts).
- TradingView throttles a symbol inside a watchlist alert that fires too often ("alerts have been
  temporarily limited due to frequent triggers"): the FVG v16.60 30s alert lost MES1! (and 6A/6B/6E/
  6J/MET) for 29 h on 2026-10-07/08. fvg-mcp shows it as "no FVG alert data for Xh" on that symbol
  while Market Translator and the relay keep flowing. Restarting the alert (connector
  `mcp-tv-restart-alerts`, or Save in its dialog) clears it.
- Jake's preferences: plain language, short answers, bottom line first; do the work rather than
  give instructions; only hand him what needs his credentials.
- Claim to verify, not assume: "12% per week". The log decides.
