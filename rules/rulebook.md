# Fractal Effects Rulebook (AI layer)

Source of truth, in priority order: (1) `amendments.md` (rule changes Jake approved),
(2) this file, (3) `live_rules.md` (rules pulled from the 12 live sessions), (4) the course.
The live sessions are newer than the course videos; where they conflict, the live sessions win.
The "Reversal Set Up" video (Oct 2026) is the newest material and overrides older notes on
white lines, reversal zones and 2DB.

The rules engine (fvg-mcp) has ALREADY found this setup mechanically: a Market Translator
signal armed it, and the FVG cascade (5m -> 1m -> 30s, or 1m -> 30s) completed with a close
over the series. Your job is NOT to re-detect the cascade. Your job is the judgment the code
cannot do: is this one of the setups the instructor would actually take?

---------------------------------------------------------------------------------------------

## 1. What's on the chart

Market Translator (MT)
- M below price = fake move down, market wants UP. M above price = market wants DOWN.
- DB at a broken high/low = continuation in the break direction ("dealer reveals its hand").
  Trade only in the DB direction, only after a retracement back into the range.
- 2M = Ms both sides. ~70% chance price returns to the first untouched 5m FVG between the Ms,
  then continues in the direction of the FIRST M. A second M does not flip the bias; it means
  a retracement is coming.
- Triangle. True = M, M, then DB (price returns to the FVG between the Ms, then goes the DB
  way). False = M, DB, then M (no new information; stick with the DB; watch for a 2DB).
- 2DB = DBs both ways. Older rule: void. NEW (Reversal Set Up video): not automatically void.
  The DB whose white line gets body-closed through, with a reversal zone printed, is failing;
  the market most likely heads to complete the OTHER DB. Without that evidence, treat 2DB as
  void (indecisive market, bias both ways).
- White labelled lines (M, 2M, DB, 2DB) = each signal's REVERSAL AREA.
  - A wick through it does not count. A 5m candle BODY close through it is criterion 2 of a
    reversal (section 5).
  - For an M trade, the white M line also sits at the far end of the fake move and works as the
    M trade's target.
- Reversal zones = small green (up) or red (down) boxes the indicator paints after a body close
  through a white line. They look different from Spotlight FVGs and "stick out". They act like
  a 5m FVG / blue zone: high probability price won't pass them.
- Purple zones (Asia/London) and blue zones (NY) = algorithmic magnets. Price is drawn to them
  and stalls or rejects there ("cement wall"). Darker (maroon, dark blue) = stronger.
  Going into one: take 50% and move stop to breakeven even short of 2R.
  A retracement INTO one allows a 1m entry (skip the 5m step).
- NDOG / NWOG (aqua/green dashed) = new day / new week opening gap. Magnet and retracement zone.
- DSD high/low = average max extension. Price can run out of steam there. Aim for candle-body
  highs short of it, not the DSD line itself.
- Session colours: Asia yellow (opens 8 PM ET), London blue (2 AM ET), NY signals green, no box
  (9:30 AM ET), NY PM purple.

Spotlight
- DR box: Asia 7:30-8:25 PM, London 3:00-3:55 AM, NY 9:30-10:25 AM ET. Signal = 5m BODY close
  outside the DR. Green triangle above bar = bullish confirmation, red below = bearish. ~80%.
- A Spotlight confirmation in one direction blocks opposite trades on that index and acts almost
  like a higher-timeframe DB.
- True day = only one side of the DR broken (~80%). False day = both sides broken: stop
  trading that index.
- Opening FVG (first 5m FVG of the session; NY's is shaded green) = as strong as a blue zone.
- EMAs: red 20, aqua 50, orange 238. Retracements to the 20 EMA are fine. Below the 238,
  price tends toward the NDOG.
- Trend table (1m..D): 20/50 cross per timeframe. Trade with the higher timeframes.
- Aqua weekly lines = Tuesday's NY range; ~70% of Thursdays retrace into it.

---------------------------------------------------------------------------------------------

## 2. Hard rules (any one = SKIP)

1. No Market Translator signal armed it (trend-fallback / "ND"). Never trade ND.
2. High-impact news day, CPI/PPI/FOMC week, or a live speech in progress: demo only = SKIP.
3. Outside the window. NY: no new entries after 11:00 ET (be in by ~10:30-10:40).
   Asia: done by ~10 PM ET. London: first ~1-2 hours after 2 AM ET only.
   Hard cutoff 11:30 ET for the NY session.
4. Index has a false day, or an unresolved 2DB (see 2DB rule above).
5. DB setup with a 5m BODY close beyond that DB's white reversal line (the DB is failing).
6. No retracement (runaway), or the retracement is too shallow (above the first FVG of the
   DB leg / one candle right of the DB candle).
7. 1:3 does not fit to a real target before an obstacle (purple/blue zone, DSD, prior
   high/low, 4H FVG). 1:1.12 style trades are rejected.
8. Entering long deeper into an overhead 4H FVG (or short deeper into one below).
9. Trading against "majority rules": 2 of 3 indices (NQ, ES, YM) show a 5m DB the other way.
10. Buying the weaker index or selling the stronger one when the other index offers the
    same idea.
11. More than 5-7 candles of consolidation at the zone, or wick-to-wick candles with no
    foothold.
12. Higher-timeframe target already delivered ("the juice is drunk") and the setup is not
    complete on both indices.

## 3. Grading (only if no hard rule fired)

Must-haves: clear signal on the setup timeframe; inside the window; real retracement into a
defined zone; first FVG at each step (one compromise max, e.g. 2nd FVG of a string); 1:3 fits.

Boosters (count them):
- DB or true triangle (continuation) rather than a lone M.
- Spotlight confirmation in the same direction.
- Retracement hit 3+ confluences: opening FVG, 20 EMA, purple/blue zone, NDOG, Fib 61-79%,
  reversal zone.
- Divergence supports it (long the stronger index / short the weaker; 2 of 3 agree).
- Higher timeframe agrees (trend table 4H/D, 4H model).
- Move goes from inside the range to outside it.
- Immediate rebalance (engulfing candle) at the zone.
- Early in the session (first 30-40 minutes).

A+ = all must-haves + 3 or more boosters -> TAKE, full size.
A  = all must-haves + 1-2 boosters -> TAKE, full size.
B  = must-haves met but a downgrade applies (below) -> TAKE, reduced size.
C  = a must-have missing -> SKIP.

Downgrades (reduce size): late in the session; setup starts outside the range; only
confluence is the inverse of the opening FVG; 1m and 5m signals conflict; reversal setup (always
reduced, see section 5); 2DB resolved by the reversal-zone rule.

## 4. Management (for the record; the rules engine scores it this way)

Stop = far end of the 30s leg that contains the 30s FVG. Target 1:3.
At 2R close 50% and move stop to breakeven; runner to 3R. Going into a purple/blue zone
before 2R: take 50% and roll anyway. Exit if it consolidates 10-15 minutes right after entry
before it is safe.

## 5. Reversal setup (Reversal Set Up video, newest)

Reversals can happen on ANY signal's white line: M, 2M, DB, 2DB.
Three criteria, all on the 5m:
1. Price reached a higher-timeframe FVG (4H or daily) or swept higher-timeframe liquidity
   (highs/lows).
2. A candle BODY (not a wick) closed through the signal's white reversal line.
3. A reversal zone printed (green box = going up, red = going down).
All three -> potential reversal. Wait for price to return into the reversal zone; the zone
acts as the 5m step, so look for a 1m FVG off it, then a 30s FVG, then the close over the
series. Always REDUCED size. Same 1:3, same management; target blue/purple zones, DSD,
liquidity, or the high left by the original M.
On an M: a reversal zone after a close through the M line can be used to CONTINUE the M setup
if price ran without you; you don't need to wait for the original first FVG.
Leftover reversal zones from the previous session show whether that session's obligation
was met (e.g. an Asia zone tapped at the NY open, then the drop).

Older rule still valid as a warning: a 1m DB against a 5m M where price hit a 4H/daily FVG,
swept the M leg and left a 5m FVG the other way -> odds fall to ~50%; only take the 1m DB
trade INTO that 5m FVG and be safe by then; the next 1m FVG to print inside it decides.

## 6. What you usually cannot see (say so, don't guess)

4H/daily FVGs off-screen, news, one-tick breaks, markers on a candle still forming, the
trend table if hidden. If a hard rule depends on something you cannot see, say "unknown" and
lower confidence rather than inventing it.
