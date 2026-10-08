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
Mac screenshot ──► fractal-agent ──► OpenRouter: cheap vision model reads the chart
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
3. The latest Mac screenshot (if < 3 min old) goes to the **vision model** once; it returns a
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
   60 min before to 60 min after the release; `NEWS_BEFORE_MIN`/`NEWS_AFTER_MIN`), DB with
   retrace `none`/`shallow`, two losses this session, weekend, NY/London/Asia windows, long
   inside a bearish 4H FVG (from the price archive). `app/rules_code.py`, `app/htf.py`.
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
     value goes in `~/.fractal-agent.env` on the Mac.
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

## Mac screenshot uploader

```
cd ~/Coding/fractal-agent
bash mac/install.sh          # first run creates ~/.fractal-agent.env — paste AGENT_TOKEN
bash mac/install.sh          # second run installs the launchd job (every 30s)
tail -f ~/Library/Logs/fractal-capture.log
```

Grant Screen Recording to `bash` when macOS asks (System Settings → Privacy & Security).
The uploader (`mac/capture.sh`) captures **only TradingView windows** (the desktop app, or a
browser window whose title matches `TV_MATCH`), each one separately, even when other windows
cover them, and sends them as one set (left window first). Browser tab titles are only visible
to it if `osascript` also has Screen Recording permission; otherwise, or when no TradingView
window is open, it sends the whole screen and the vision model marks non-charts `not_chart`,
which the agent ignores. `CAPTURE=screen` restores the old whole-screen mode.
Layout assumption (set in `SCREEN_LAYOUT`): 5m charts on the LEFT, 1m on the RIGHT, MNQ and
MES visible. If TradingView is on an external monitor, set `SCREEN=2` in the env file.

## VPS screenshot capturer (tv-capture/)

Coolify app `tv-capture` (same project, base directory `/tv-capture`, volume `/data`, domain
https://tv.motivationpro.tech). Headless Chromium logged into TradingView with Jake's session
cookies screenshots the pages in `TV_PAGES` every 30 s during futures hours and posts them to
`/screenshot` with `kind=vps` and `layout=<TV_LAYOUT>`; the agent stores that layout text per
kind and the vision prompt uses it, so the Mac uploader (kind=window) and the VPS can coexist;
the agent reads whichever set is newest. Env: `AGENT_URL`, `AGENT_TOKEN`, `UI_PASSWORD`
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

Done 2026-10-07: deployed on Coolify (project fractal-agent), Mac uploader running, dashboard,
learning loop, Jev shadow scoring, news filter, spend tracking. Still open:

1. ~~Deploy + Mac uploader (above).~~ Watch one session; check `decision_detail` rows to see what
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
  Jake repointed them to `https://fvg.motivationpro.tech/webhook?token=…`. Data resumed 00:49 ET.
- Jake's preferences: plain language, short answers, bottom line first; do the work rather than
  give instructions; only hand him what needs his credentials.
- Claim to verify, not assume: "12% per week". The log decides.
