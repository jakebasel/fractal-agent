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

There is no order-placement code in this repo. Keep it that way until Jake says otherwise.

## Rules

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
Layout assumption (set in `SCREEN_LAYOUT`): 5m charts on the LEFT, 1m on the RIGHT, MNQ and
MES visible. If TradingView is on an external monitor, set `SCREEN=2` in the env file.

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

1. Deploy + Mac uploader (above). Watch one session; check `decision_detail` rows to see what
   the vision model actually read off the screen. Tune `VISION_PROMPT` in `app/prompts.py`
   until it reliably reads white lines and reversal zones. This is the weakest link.
2. Confirm fvg-mcp's `entries` rows for MNQ1!/MES1! carry `f_pnl_r` within ~2h (they did on
   2026-10-05). `scoring_health` on fvg-mcp shows whether scoring is on time.
3. News filter: rule §2.2 (news days) is not enforced by code yet. Add an economic-calendar
   check (high-impact USD events) as a code hard rule.
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
