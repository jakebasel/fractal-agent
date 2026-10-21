# Approved amendments

Rule changes Jake has approved. These override everything else.
The agent proposes changes in its lessons; nothing lands here without Jake's OK.

(none yet)

## 2026-10-07 — Session times are preferences, not hard rules (Jake)
The whole session is tradeable. "First two hours of London", "Asia done by 10 PM", "NY after
11:00" were the instructor's time preference (he values his time; odds fall later), not
rules. They are DOWNGRADES (reduce size, "late in the session"), never skips. The engine's
own session-window flag (fvg-mcp `in_window`; its NY window ends at 12:00 ET so every NY PM
entry carries it) is a downgrade as well, not a skip. The weekend and the "two losses this
session" rule remain hard.

## 2026-10-07 — News: red-folder bracket, not the whole day (Jake)
Rule §2.2 applies only to red-folder (high-impact) USD releases and only inside a bracket
AFTER the release: from the release time until 2 hours after it (`NEWS_AFTER_MIN` = 120;
`NEWS_BEFORE_MIN` = 0, the hour before the release trades normally, reduced size per the
instructor is a downgrade, not a skip). Restated by Jake 2026-10-07 evening after the first
version wrongly used 60 min before to 60 min after. Outside the bracket the day trades
normally; London is unaffected by a US release at 8:30 or 14:00 ET. The "CPI/PPI/FOMC week = demo only" reading is retired
(a hypothesis tests it). A live speech is still untradeable while it runs (judgment call for
the model when the chart read or news list shows one).

## 2026-10-16 — CPI/PPI release days: no US-related assets all day (Jake)
Follows the instructor (live sessions 2026-10-15: "Do not be trading any US-related assets on PPI
day, CPI day. It's just not smart."). On any ET day with a CPI or PPI release (core or headline),
US-related assets (NQ, ES, YM, RTY and their micros; NAS100, US500, US30, US2000) are SKIP for
the whole day, every session, before and after the release. Supersedes the 2-hour bracket of
2026-10-07 for CPI/PPI only; other red-folder USD releases keep the bracket. Non-US assets
(gold, FX, oil, Japan 225, Europe) trade normally outside the bracket. The rest of a CPI/PPI
WEEK is not affected.

## 2026-10-07 — 2DB is never traded (Jake)
A 2DB (two Double Breaks) is a SKIP, always. It is the overarching reason: when a 2DB also
falls outside the window or has a bad retracement, the skip is reported as "2DB", not as the
window. Supersedes §2.4 "unresolved 2DB" and the §5 reversal-zone resolution of a 2DB. Scope (from
the Signal Legend): the skip holds on that index and timeframe until the next session; a 1m
2DB voids 1m plays only. OPEN POINT for Jake: does "no other logic for a new set up until next
session" also exclude a Reversal Set Up off the 2DB's white line in the same session? Until
answered, the agent treats it as excluded (the stricter reading).

## 2026-10-08 — Signal priority on a timeframe (Jake, verified against the transcripts)
On a given timeframe (1m or 5m) the NEWEST Market Translator signal replaces the previous one:
once a new signal prints, setups built off the old signal can no longer be traded. The only
case where two signals stay tradeable together is two Ms in the SAME session (the 2M
configuration). A DB is always exclusive: it replaces whatever was armed before it on that
timeframe. (fvg-mcp's `live_arms()` already implements this; the agent must never take an
entry whose arming signal has been superseded.)

## 2026-10-08 — A Market Translator signal expires after 6 hours (Jake)
A signal is live for at most 6 hours after it prints. An entry whose arming signal was older
than 6 hours at the entry bar was taken off a dead signal and is not a strategy trade.
fvg-mcp enforces it live (`strategy.signal_max_age_h = 6`) and the Analysis book excludes
such entries as "stale signal"; the agent must never take one.

## 2026-10-08 — Re-entries must re-tap the original zone (Jake)
There is no cap on the number of entries off one signal, but a later leg is only valid if
price came back and re-tapped the ORIGINAL 5m/1m zone after the previous trade closed. The
only time the original zone can be skipped is when it was invalidated first; then the next
presented zone is the one to tap. fvg-mcp enforces it live and the Analysis book excludes
legs that did not re-tap ("no re-tap"); the agent must never take one.

## 2026-10-08 — What counts as a tap (course wording; fvg-mcp setting noted)
The course never gives a depth: the instructor paints the box and waits for the market to
"come back and touch it". Any contact with the zone is a tap; a wick to the edge counts and
the body does not have to enter. fvg-mcp follows that for the first presented gap. For the
SECOND presented gap (its "first two gaps" setting, `fvg_gaps = 2`) it also requires the tap
to reach the gap's midpoint — Jake's own 2026-08-11 setting, not a course rule. Open for Jake:
drop the midpoint requirement to match the course exactly.

## 2026-10-08 — The core book (Jake: "sync the Live Dashboard with the Analysis tab")
One book, everywhere: a trade counts only if its arming signal was not superseded before the
entry (signal priority above), the signal was under 6 hours old at the entry, and any later
leg re-tapped its zone. The fvg-mcp Live Dashboard History (default "core rules only"), the
Analysis tab and this agent's Symbols tab all apply the same three exclusions, plus the
standing ones (ND and Gold Strategy are never aggregated with real signals).

## 2026-10-20 — DB plays: a NEW gap after the retracement, on the signal's timeframe (Jake)
Applies to the 1m and the 5m DB play, either direction. The sequence is:
DB prints -> price retraces back into the DB leg (its FVG, or past the DB candle when the leg
has none) -> a NEW FVG in the DB's direction prints on the signal's timeframe AFTER that
retracement (bearish DB -> new bearish FVG; bullish DB -> new bullish FVG) -> it is tapped ->
the lower timeframe steps (5m play: 1m, then 30s; 1m play: 30s) -> body close over the series
-> enter. The gap price retraced INTO is the retracement, not the entry gap, and a gap that
printed before the retracement finished does not count. Retracement done but no new gap yet =
not ready, however good the rest looks (Jake 2026-10-20, US30 1m DB short: "the retracement
has occurred, and we don't have a new bearish ... fair value gap"). fvg-mcp's engine enforces
it from 2026-10-20: a DB arm only enters from its after-retracement hunt.
When a DB's retracement has run into a reversal zone instead, check the Reversal Set Up (§5)
for the other side before calling the DB direction (same example: a long off the printed
reversal gap).

## 2026-10-20 — Missing data is a downgrade, never a skip by itself (Jake)
Overrides §3's "C = a must-have missing -> SKIP" where "missing" only means the data is absent,
stale or could not be verified (no chart read, an old screenshot, an empty HTF feed, a field the
engine does not fill, a news calendar that did not load). That is a B: TAKE at reduced size and
list it under "unknowns". C / SKIP needs EVIDENCE that a must-have FAILS (the chart or the
engine shows no tap, no foothold, a third compromise, 1:3 does not fit) or a hard rule (§2)
firing. Jake 2026-10-20: "stop missing data from forcing a skip" -- 62 of 62 skips 10/13-10/20
were C, half of them on a retracement field the engine only fills for DB signals.
Retracement on an M / 2M: the engine's quality grade is DB-only, so a null there is NOT missing
evidence. The M's retracement is the pullback into the first presented FVG, which the stages
show. A DB entry only exists after the retracement completed and a new same-direction gap printed.
