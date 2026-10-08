# Fractal Effects Rulebook (AI layer)

Source of truth, in priority order: (1) `amendments.md` (rule changes Jake approved),
(2) this file, (3) `live_rules.md` (rules pulled from the 7 live-session transcripts we have),
(4) the course. The live sessions are newer than the course videos; where they conflict, the
live sessions win. The "Reversal Set Up" video is the newest material on white lines and
reversal zones; it does NOT reopen 2DB (see amendments: 2DB is never traded).
Audited against the course material on 2026-10-07 (`reports/rules_audit_2026-10-07.md`).

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
- Triangle = an M in one direction and a DB in the other (M, [M], DB): both point the DB way;
  price returns to the FVG between the Ms, then goes the DB way. A later M after a DB is just
  a second M (retracement coming; if in a trade, secure profits and roll the stop).
- 2DB = DBs both ways = SKIP, always (amendments, Jake 2026-10-07). "No other logic for a new
  set up should form after this point, until next session" on that index/timeframe. A 1m 2DB
  voids 1m plays; the 5m may still set up. The 2DB's reversal zone is information about which
  DB is more likely to complete and the next session's obligation, never an entry trigger.
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
  Going into one before 2R: be safe (stop to breakeven) by the time price reaches it; a
  partial is optional; the zone is a valid take-profit.
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
- Opening FVG (first 5m FVG of the session inside the DR; green if bullish, red if bearish)
  = as strong as a blue zone.
- EMAs: red 20, aqua 50, orange 238. Retracements to the 20 EMA are fine. Below the 238,
  price tends toward the NDOG.
- Trend table (1m..D): 20/50 cross per timeframe. Trade with the higher timeframes.
- Market Translator is designed for 15m, 5m and 1m. Signals print on the 30s but the fractal
  breaks down there; it is not designed for 1h or above (false readings). Zeus covers D/4H/15m.

Signal priority (amendments 2026-10-08): on a timeframe the newest Market Translator signal
replaces the previous one; setups off a superseded signal are not traded. Only two Ms in the
same session stay armed together (2M); a DB always replaces what came before it.

The models, step by step (the golden rule: if ANY step doesn't happen, there is NO entry)
- M: M prints -> first 5m FVG opposite the fake move, tapped -> first 1m FVG, tapped -> first
  30s FVG, tapped -> body close over the series -> enter. Target: liquidity / zone / the M line.
- DB: DB prints -> retracement back into the range (an FVG in the DB leg, or, when the leg is a
  single candle with no FVG, the midpoint of that candle = "order block", counted as the 5m
  step; immediate rebalance; a 5m FVG in the DB direction) -> 5m -> 1m -> 30s -> close ->
  enter, in the DB direction only. A fresh 5m DB = 70-80% chance of a retracement back into
  the range: never enter against it; if in a trade, be out.
- 1m play: 1m signal, immediate rebalance, 1m FVG, 30s FVG, close. Target: the DB top on the
  5m (the move that makes the 5m DB). Stick to the signal's timeframe.
- Spotlight (DR) play, standalone: 5m body close outside the DR (confirmation) -> retrace into
  the range to an FVG / 20 EMA / Fib 61-79% -> 1m FVG, engulfing, 30s FVG -> close. Stop a few
  ticks beyond the rejecting candle. Target 1-1.5 standard deviations. No setup within one
  hour of the range forming = pass on that session. Must align with the 4H session model.
- Aqua weekly lines = Tuesday's NY range; ~70% of Thursdays retrace into it.

---------------------------------------------------------------------------------------------

## 2. Hard rules (any one = SKIP)

1. No Market Translator signal armed it (trend-fallback / "ND"). Never trade ND.
2. From a red-folder (high-impact) USD release until 2 hours after it (amendments
   2026-10-07; nothing before the release), or a live speech in progress: SKIP. The rest of the
   day trades normally; London is not affected by US releases.
3. The weekend. Time within a session is never a skip (amendments 2026-10-07): late in the
   session (NY after ~10:30-11:00, London after the first couple of hours, Asia after ~10 PM)
   and the engine's `in_window: false` flag are downgrades, see §3.
4. 2DB on that index/timeframe this session (never traded), or the index has a false day.
5. DB setup with a 5m BODY close beyond that DB's white reversal line (the DB is failing).
6. No retracement (runaway), or the retracement is too shallow (above the first FVG of the
   DB leg / one candle right of the DB candle).
   Directional filter: a DB or a Spotlight confirmation one way means that index is traded
   that way only ("either we trade in that direction or we don't trade that asset").
7. 1:3 does not fit to a real target before an obstacle (purple/blue zone, DSD, prior
   high/low, 4H FVG). 1:1.12 style trades are rejected.
8. Entering long deeper into an overhead 4H FVG (or short deeper into one below).
9. Trading against "majority rules": 2 of 3 indices (NQ, ES, YM) show a 5m DB the other way.
10. Buying the weaker index or selling the stronger one when the other index offers the
    same idea.
11. No foothold: wick-to-wick candles with no FVG at the entry ("they don't want you in"),
    or price has ripped through the same FVG two or three times already. (5+ candles of
    consolidation at the 30s FVG is NOT a skip by itself: it is power-of-three risk, see §3.)
12. Higher-timeframe target already delivered ("the juice is drunk") and the setup is not
    complete on both indices.
13. Two losses already this session: stop ("anything more than that and you're technically
    gambling"). Checked in code from the paper book.
14. 10-11 AM ET manipulation (4H model): if the 10 AM 4H candle manipulates (sweeps a high/low
    or taps a 4H FVG), avoid entries even with a DB in the blue zone. Usually not visible to
    the engine; say "unknown" unless the chart read shows it.

## 3. Grading (only if no hard rule fired)

Must-haves: clear signal on the setup timeframe; inside the window; real retracement into a
defined zone; first presented 5m FVG, no exceptions; one compromise allowed on the 1m or 30s
(the second of a string, never a third); 1:3 fits; a real foothold (an FVG at the entry).
Power of three: 5+ candles at the 30s FVG = wait one more candle to close outside the range
after the closure over the series, and use the safer stop (candle 1 of the 30s FVG pattern).
30s FVG discipline: after the tap, the first 30s FVG printed is the one used; an immediate
rebalance (close over the series) is the entry and that line is never moved afterwards. If
price runs the 30s again without closing, take a NEW 30s FVG off the new leg (tap + close),
or keep the old one and demand a closure over the same old line.
Never pair a signal against power of three (a signal on the breakout of a 5+ candle
consolidation is suspect).

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

Live-session plays and targets to look for (the instructor's habits, not extra rules):
- Blue/purple zone bounce: a retracement INTO the NY blue zone (from 9:30 ET, especially if
  untouched) or the Asia purple zone, then the full cascade off it; the zone is the foothold
  and the opposite side / next liquidity is the target. Higher probability than a mid-air entry.
- Target the higher-timeframe liquidity in play: prior day/session high or low, DSD, 4H/daily
  FVG, the London/Asia obligation, the high left by the original M. Aim for candle-body
  highs short of a DSD line. 1:3 must fit BEFORE that obstacle.
- Use the sister pair's signal: a US500 (MES) DB can be the reason to look for the same trade
  on NAS (MNQ) if NAS is the stronger index for a long (weaker for a short), and vice versa;
  "same idea on both" with 2 of 3 agreeing is a booster; a DB the other way on the pair is a
  block.
- Spotlight comes from the CHART READ only (no feed carries it): confirmation direction =
  directional filter for that index; true/false day; opening FVG as a blue-zone-strength
  level; the DR box edges as liquidity. If the read has no Spotlight, say so.

Downgrades (reduce size): red-folder news day, outside the skip bracket (erratic price
action before the release: reduced lot or stay out); late in the session; setup starts outside the range; only
confluence is the inverse of the opening FVG; 1m and 5m signals conflict; reversal setup (always
reduced, see section 5); Friday ("Trap Friday": expect a 20-30% retrace of the weekly candle
after an HTF level is hit); all-time highs (no liquidity above, a DB can simply drop: roll early).

## 4. Management (for the record; the rules engine scores it this way)

Stop = far end of the 30s leg that contains the 30s FVG. Target 1:3. Fixed % risk per trade
(the course uses 1% to make 3%); "reduced" = half of that.
At 2R close 50% and move stop to breakeven; runner to 3R. Going into a purple/blue zone
before 2R: be safe (stop to breakeven) by the time price reaches it, partial optional.
If price reaches a 4H/daily FVG or HTF liquidity and consolidates there before the trade is
safe, exit at breakeven. A 5m DB against a 1m play: roll the stop or close. Divergence: when
EITHER index crosses your take-profit level first, close the one you are in (a delivery for
both). If a second M prints while you are in a trade: secure profits, roll the stop.
Kill condition from the course: a candle BODY closing through the consequence encroachment
(midpoint) of the FVG you are trading against your direction.
Spotlight confirmation ahead: when price crosses the DR edge (past the implied dealing
range) a confirmation can print on the close and often brings a retracement: take 50% (or
reduce to a 10% flyer) before it prints; on the confirmation, be out or flyer only. Be in a
safe trade by the time price reaches the next gap, zone or 4H FVG.

## 5. Reversal setup (Reversal Set Up video, newest)

Reversals can happen on an M, 2M or DB white line (not a 2DB: that index is done for the
session).
Three criteria, all on the 5m:
1. Price reached a higher-timeframe FVG (4H or daily) or swept higher-timeframe liquidity
   (highs/lows). (2M: the return-then-continue play needs NO HTF FVG to have been hit; trading
   INTO the untouched FVG in the second M's direction is itself a play.)
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
