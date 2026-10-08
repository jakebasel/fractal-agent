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

## 2026-10-07 — 2DB is never traded (Jake)
A 2DB (two Double Breaks) is a SKIP, always. It is the overarching reason: when a 2DB also
falls outside the window or has a bad retracement, the skip is reported as "2DB", not as the
window. Supersedes §2.4 "unresolved 2DB" and the §5 reversal-zone resolution of a 2DB. Scope (from
the Signal Legend): the skip holds on that index and timeframe until the next session; a 1m
2DB voids 1m plays only. OPEN POINT for Jake: does "no other logic for a new set up until next
session" also exclude a Reversal Set Up off the 2DB's white line in the same session? Until
answered, the agent treats it as excluded (the stricter reading).
