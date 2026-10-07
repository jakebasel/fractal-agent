# Morning report — 2026-10-07 (overnight session)

Bottom line: everything from the plan is deployed and running on paper. The first real data
says the rulebook, applied mechanically, has **not** been profitable over the last 10 weeks
(286 trades, −35R), and the live-session transcripts contain **zero** trades the instructor
actually took. Neither kills the project; both change what to measure next. Details below.

## 1. What is running now

- **Agent** at https://agent.motivationpro.tech (paper only). Dashboard login = the password
  you typed. Tabs: Overview, Setups (with the screenshots each decision used and the scanner's
  spotted setups), Learning (hypotheses with Approve/Reject, lessons), Breakdown (play,
  timeframe × signal, session, config, grade, booster, hard rule, vision accuracy, Jev),
  Spend, Rules, Backtest.
- **Every decision records**: timeframe × signal × kind play (e.g. `5m DB continuation`),
  the rulebook version it was made under, all hard rules that fired (overarching reason first:
  2DB, ND, news, retracement, window), Jev's probabilities, vision trust score, news check.
- **Hard rules in code** (no AI, no cost): 2DB (your rule, in `rules/amendments.md`), ND,
  high-impact USD news today / CPI-PPI-FOMC week (ForexFactory calendar), DB with no or
  shallow retracement, weekend, NY after 11:00, London after the first 2h, Asia after 10 PM,
  engine out-of-window flag.
- **Learning loop**: proposals → hypotheses → shadow-tested on the same trades (past 60 days
  and new) → compared with the agent and the core strategy → you approve on the dashboard →
  I commit to `amendments.md` (new rules version). Three seeds are running.
- **Jev** (shadow): ~100 ms, scores each judgment hard rule, P(TAKE), grade, play kind.
  Switch to `JEV_MODE=gate` once the Breakdown tab shows it agreeing with the agent.
- **Chart scanner**: every 5 min in 02:00–04:00, 09:25–11:00, 20:00–22:00 ET, when the screen
  changed, asks for plays the engine never arms (reversal set ups, 1m plays, zone plays).
  "Ready" ones with levels are scored 2.5h later against fvg-mcp's price archive with the same
  2R + runner management. Logged, never traded.
- **Spend guard**: `DAILY_BUDGET_USD=1.50`. Past it, shadow tests and the scanner pause;
  live decisions always run. Tonight's spend so far: under 1 cent.
- **Management rules** (your note tonight): every TAKE now carries a management plan
  (be safe by, partial at, kill conditions) that the lesson step is judged against, and every
  settled trade is re-scored on the price tape with the instructor's in-trade rules (a 5m DB
  against the play closes it). The dashboard's Books table shows "with his management rules"
  next to the mechanical 2R + runner result, for both the agent and the core strategy. Other
  management rules (zone ahead → partial early; consolidation 10–15 min → exit; be safe before
  the next obstacle) are in the rules text the model reads; scoring them on the tape needs zone
  levels, which is the HTF-FVG-from-archive item in section 4.
- **Mac uploader**: finds the TradingView tab by URL through Chrome, captures only that window
  (works while other windows cover it), tells the dashboard when the tab is in the background
  or TradingView is closed instead of sending the wrong screen.

## 2. Findings from the data

### 2a. Ledger backtest (fvg-mcp, MNQ1!/MES1!, Jul 29 – Oct 5, 2,046 scored trades)
Protocol: `tools/backtest_protocol.md` (70/30 time split at Sep 3, fixed pass rule, every tweak
logged, multiple-testing bar). Report: Backtest tab / `reports/backtest_latest.json`.

| book | n | win% | avg R | total R | max DD |
|---|---|---|---|---|---|
| every engine entry (ND excluded, see below) | 1148 | 36.0 | +0.01 | +9 | −61 |
| after the code hard rules (= the rulebook, mechanically) | 286 | 32.9 | −0.12 | **−35** | −52 |
| removed by the hard rules | 862 | 37.0 | +0.05 | +44 | −42 |

What the hard rules removed: London-after-2h 239 trades +39R; 2DB 27 trades +23.5R (70% win);
NY-after-11 108 trades −10R; out-of-window 244 −10R; DB with no retrace 103 −5R.

Read this carefully before reacting:
- **ND entries are excluded from "core".** The first run showed 898 ND trades at +491R, all
  before Sep 3. fvg-mcp's history explains it: "ND trend-fallback retired by default"
  (2026-08-11) and "ND toggle, default off" (08-20). ND is not part of the strategy and fvg-mcp's
  own analysis drops it, so the backtest does too. Not an edge.
- **The best tweak is "walk away after −2R in a day"** (the instructor's own rule): train
  +14.5R, holdout +13.3R, ~105 trades affected, drawdown not deeper, losers cut on both halves.
  It passes every check except the multiple-testing bar (holdout t = 2.2 vs 2.9 required after
  11 tweaks tried), so the protocol calls it borderline, not proven. "Walk away after −1R" is
  similar and weaker. Both are on the live dashboard as computed books (Agent/Core +
  walk-away), no model call. Recommend: keep it as the leading candidate and approve it into
  amendments.md once the live book agrees over a few weeks.
- "5m signals only" (train +16R, holdout +14R) and "allow out-of-window entries" (holdout +22R)
  are *inconclusive*: real on both halves but failing one check each. Keep watching live.
- Friday, NY-after-10:30 half size, deep-retrace-only, DB-only, skip-NYPM: inconclusive or fail.
- **The 2DB and London rules cost money in this sample.** Small n (27 / 239) and the ledger
  cannot see the chart, so this is a data point, not a verdict. The live agent keeps the
  counterfactual R of every code skip, so the "Hard rules" table on the dashboard will keep
  answering this with real trades.
- The rule-compliant book is negative in both halves. If the strategy has a 12%/week edge, it
  is not in the mechanical part the ledger can see. It has to be in what the chart adds (lines,
  zones, Spotlight, divergence) or in discretion. That is exactly what the live agent measures.

### 2b. Live-session transcripts (7 sessions, June/July **2025**)
Labelled by two helpers (no API spend): `knowledge/labels/*.json`, 97 events, 93 stated rules.
- **The instructor took zero trades in all seven sessions.** 23 explicit skips, 10+ waits.
  So there is no "his takes vs the engine" dataset; there is a "his skips and his rules"
  dataset. The dates are 2025, before fvg-mcp's archive, so no alignment with the ledger.
- The discretion he states (now in `knowledge/` for the decision prompt): tight candles with
  no foothold = engineered whipsaw, skip; no reversal shorts after a shock wick; skip a valid
  first FVG when it is a shallow retracement inside a 4H FVG; where the 30s FVG forms matters;
  "juice already drank" → reduced size and both pairs must complete; news-candle DB is void;
  weaker pair not bought; one FVG compromise max, then none; location inside the 4H FVG kills
  setups even when the mechanical steps are present.
- **Useful next step**: more sessions where he actually trades. If the Kinveo recordings
  include later live sessions, those are the ones to transcribe.

## 3. Research notes (what the field says, applied here)
- Backtests: 30 trades per free parameter; a >50% drop from in-sample to out-of-sample is the
  standard overfitting flag; walk-forward; count the trials. All four are now in the protocol.
- Vision models on candlestick charts (two 2026 benchmarks): they mostly extrapolate the
  visible trend and are poor at precise levels. Applied: the agent now scores every chart
  read against the engine's price (vision trust score), the vision prompt is limited to
  discrete markers (lines, boxes, labels), and the next step should compute 4H/daily FVGs from
  fvg-mcp's archived prices instead of asking the vision model.
- LLM trading-agent evaluations (2026): general model quality does not predict trading
  results; risk control does. Applied: nothing yet. Suggested: a daily-loss rule (stop after
  −2R or two losses in a session, which is also what the instructor does: "walk away") as a
  hypothesis, measurable in the ledger and live.

## 4. Suggested changes (ready for your yes/no)
1. **"Walk away at −2R/day"** is the leading candidate (his rule, not data-mined; helps on
   both halves; borderline on the multiple-testing bar). Approve after a few weeks of live
   confirmation.
2. ~~Compute higher-timeframe FVGs from archived prices~~ Done tonight (`app/htf.py`): 4H and
   daily gaps from fvg-mcp's tape go into every decision with the entry's position relative to
   each; long inside a bearish 4H FVG / short inside a bullish one is now a code skip (rule
   2.8). Caveat: the archive only has whole days, so today's 4H candles are missing until the
   day is archived; the context says how old the data is.
3. ~~Ask fvg-mcp what changed~~ Answered: ND was retired on 2026-08-11; excluded.
4. **Transcribe live sessions where he trades.** The seven we have are watch-only.
5. **Keep Jev in shadow for a week**, then gate. Keep the scanner at 5 min; raise the budget
   only if the Spend tab shows it pausing during NY.
6. Sections 5 and 6 below (rules audit, code review) have their own lists.

## 5. Rules audit against the course material
A helper read all ~700 KB of course, lessons, SOP and live transcripts against `rules/` and the
code. Full report with verbatim quotes: `reports/rules_audit_2026-10-07.md`. Applied tonight
(rules text + code, all tests pass):
- **2DB**: every source statement is absolute ("we do not mess with this", "DO NOT ENTER").
  Rulebook §1/§2.4/§3/§5 and live rules no longer say a 2DB can be "resolved"; the scanner now
  reads the amendments too. Scope added: holds until the next session on that index/timeframe;
  a 1m 2DB voids 1m plays only. **Open point for you** (in amendments.md): does the 2DB also
  exclude a Reversal Set Up off its white line in the same session? The agent assumes yes
  (stricter) until you say otherwise.
- The prompt line that let a Reversal Set Up video passage override the rulebook is gone;
  priority is amendments → rulebook → live rules → passages.
- Wrong facts fixed: MT works on 15m/5m/1m, breaks down on the 30-**second** chart (not "30m
  up"); 5+ candles of consolidation is power-of-three risk (wait one more candle, safer stop),
  not a hard skip; opening FVG colour is by direction, not session; into a zone before 2R =
  roll the stop, partial optional; "false triangle" and the "10–15 minute exit" had no source
  and are gone; the one-FVG compromise never applies to the 5m.
- Missing rules added: max two losses per session (now a code hard rule from the paper book),
  fixed % risk, the divergence take-profit rule, directional filter, 10–11 AM manipulation
  (4H model), the explicit M / DB / 1m / Spotlight step lists ("if any step doesn't happen,
  there is no entry"), 2M "into the gap" play, second-M-while-in-a-trade management,
  consequence-encroachment kill condition, Trap Friday, all-time-highs caution.
- Spotlight (DR) is a standalone play in the course; it is now a play kind the scanner can
  report (the engine would call it ND).
- Code fixes: Asia window now also catches 00:00–02:00 ET; weekend = Saturday and Sunday
  before 6 PM ET (futures reopen), same in the scanner.
- Nine live-rule items were not found in the 7 transcripts we have (majority-rules 2-of-3,
  AMD earnings, 1.96R, stop-to-midpoint at ATH, "one candle to the right", etc.). They are
  kept but marked *unverified* at the top of `live_rules.md`. If they came from sessions we do
  not have, those transcripts would settle it.

## 6. Code review findings and what was fixed
A second helper reviewed every new file for bugs (threading, time zones, retries, auth, maths)
and reproduced the serious ones. All fixed and tested (65 tests), deployed:
- **Dashboard rendering**: the Backtest card read a key I had renamed, so the JavaScript
  died there and the Learning / Setups / Breakdown / Spend tabs would have come up empty. Fixed
  and guarded; "ago" times now come from epoch timestamps (no DST edge).
- **Credit-burning retry loops**: a failing vision call inside a scan window would have been
  retried every 15 s (4 calls/min) with no budget check; a single trade whose shadow call
  always fails would have cost one call per tick forever and blocked every other shadow test.
  Both now cache/count failures and move on.
- **One crash stalling the loop**: an unexpected error inside a decision would have retried
  every 15 s and blocked settlement, scanner and shadow tests until the entry aged out. Now it
  becomes an ERROR row, retried while the entry is fresh; ERROR/MISSED rows still settle so
  the core book stays complete (otherwise "core" quietly excluded the days the service
  misbehaved).
- **SQLite**: the HTTP thread and the agent thread shared one connection; a commit on one
  could silently truncate a read on the other (reproduced: 280 of 600 rows). Now one connection
  per thread with WAL.
- Also: half-uploaded screenshot batches no longer get read as complete; tape downloads for
  4H FVGs happen outside the live decision; the opposing-5m-DB lookup covers 400 events (60
  was too few for 2 hours of MNQ+MES); non-ASCII passwords returned 500 instead of 401; the
  backtest's "allow" tweaks no longer re-admit trades another rule also removes; hypothesis
  tables count trades taken (n) the same way as the headline book.
- Open (not fixed, low risk): the dashboard cookie is a 30-day bearer with no server-side
  revocation (log out only clears the browser); `/api/dashboard` reloads the whole table on
  every refresh (fine at today's size).

## 7. macOS permissions and startup items this project uses
- **Screen Recording**: `/bin/bash` (the uploader, under launchd). Granted.
- **Automation (control Google Chrome)**: `bash` → Chrome, so the uploader can ask which
  window has the TradingView tab. Granted on first run tonight (if a prompt is still pending,
  it is this one). Also Claude/Terminal → Chrome when I tested by hand.
- **Startup item**: `~/Library/LaunchAgents/com.jake.fractal-capture.plist` runs
  `mac/capture.sh` every 30 s while you are logged in. Remove with `bash mac/install.sh uninstall`.
- Nothing uses the microphone or audio recording. If macOS asked for audio, that was another
  app (Zoom/GoToMeeting/RustDesk are also in your login items).
- Local secrets: `~/.coolify.env` (Coolify API token, AGENT_TOKEN, dashboard password) and
  `~/.fractal-agent.env` (AGENT_TOKEN). The OpenRouter key is only in Coolify.
- No terminal restart was needed: permissions apply to the launchd job on its next run.

## 8. Afternoon additions (2026-10-07, after you woke up)
- News rule: red-folder USD releases only, skip inside ±60 min; session times are downgrades,
  never skips (your rules, in amendments.md). The fvg-mcp window flag is a downgrade too.
- Jev playbook generated from the rulebook (36 questions); Jev scores engine setups, the
  scanner's forming setups and re-evaluated skips. Skips are re-decided automatically when the
  rules change (re-evaluation line on each card).
- DeepSeek V3.2 is the decision model (V4 Pro thinks its budget away; kept as fallback).
- Live-session rules from the FOMC-minutes session (2DB → 70-80% retrace, order-block
  midpoint, 30s FVG discipline, Spotlight-confirmation protection) in rules + knowledge.
- Backtest extended with the full MT history and the red-folder calendar: none of the
  ledger-testable live-session rules moves the needle; "walk away at −2R/day" remains the best.
- Hermes Agent reviewer deployed (Coolify app hermes-reviewer): reviews every settled trade
  (wins and losses) on the take/skip error matrix and the exit, with screenshots, posts reviews
  and proposals; OpenRouter prompt caching on, compact packets, 2 trades per run.
- Dashboard: pending/armed engine setups panel with the rule that would skip them, engine
  feed health (MES chart FVG alert stale since 05:05 ET: TradingView-side fix), NY PM scan window.
