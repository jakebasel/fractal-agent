# Rules audit — Fractal Effects rulebook vs source material

Audited: `rules/rulebook.md`, `rules/live_rules.md`, `rules/amendments.md` (as modified 2026-10-07 01:44),
`app/rules_code.py` (as modified 01:44, i.e. the version with `hard_rules()` and the 2DB check),
`app/prompts.py` (PLAYS, DECISION_SYSTEM, SCAN_SYSTEM).

Source read in full: 9 course transcripts (`knowledge/course/`), 7 mini lessons incl. "Reversal Set Up"
and "Live Sessions (raw transcripts)" (`knowledge/lessons/`), SOP + strategies PDF text (`knowledge/reference/`).

Two facts about the source that affect several findings:

- The live-session file contains **7 sessions** (its own header: "Combined from 7 unique session files"), dated
  June 13, June 23, June 24, "Night 7", July 14, July 16 (two parts). `live_rules.md` says it was "Pulled from the
  12 live-session transcripts" and `knowledge/README.md` says 12 sessions / ~440 KB. Several live_rules items could
  not be found in the 7 sessions provided; they are listed in §6 as unverifiable, not as wrong.
- The "Reversal Set Up" transcript header says "transcript pulled from Google Drive's auto-transcript, 2026-10-07".
  That is the pull date, not the video date. `rulebook.md` line 6 asserts the video is "(Oct 2026)" and "the newest
  material". Nothing in the source supports that dating; the same reversal-zone model also appears in the older
  strategies PDF (`fractal_effects_strategies.txt`, "MARKET TRANSLATOR — REVERSAL STRATEGY").

---

## 1. Wrong — rule text that contradicts the source

### W1. 2DB is treated as tradeable / "resolvable" (rulebook §1, §2.4, §3, §5; live_rules §5; PLAYS)

Rule text:
- rulebook §1: "2DB = DBs both ways. Older rule: void. NEW (Reversal Set Up video): not automatically void. The DB
  whose white line gets body-closed through, with a reversal zone printed, is failing; the market most likely heads
  to complete the OTHER DB. Without that evidence, treat 2DB as void"
- rulebook §2.4: "Index has a false day, or an unresolved 2DB (see 2DB rule above)."
- rulebook §3 Downgrades: "2DB resolved by the reversal-zone rule."
- rulebook §5: "Reversals can happen on ANY signal's white line: M, 2M, DB, 2DB."
- live_rules §5: "2DB (older rule): voids the setup ... See the rulebook for the newer reversal-zone resolution."
- prompts.py PLAYS: `"2DB": "two Double Breaks; resolved by the reversal-zone rule"`

Source (every statement of the rule is absolute):
- `course/Market Translator.txt`: "you can get a 2 DB. This is where you get a double break in both directions. Now
  this would avoid the trade setup." ... "Which one do you stick to? Well this is where we avoid the trade completely.
  We either move on to another asset entirely or we wait for the next session. But we do not mess with this." ...
  "We void the trade setup. So once you get this, that's it. I'm done looking at this particular session or this
  particular asset."
- `lessons/Signal Legend.txt`: "2DB — Void any previous set up and no other logic for a new set up should form after
  this point, until next session."
- `reference/sop.txt` §03: "2DB Double DB (both directions) — Voids setup entirely. DO NOT ENTER. Walk away."
  §08 Immediate Stop Conditions: "2DB signal appears → setup voided, do not enter". §09 checklist item 2:
  "Signal type — is it voided by 2DB?"
- `lessons/Core Strategy Walkthrough.txt`: "2DB. If we then drop and it turns into a 2DB, we avoid it: too many
  directional biases, it's tricking us too many times. M, 2M, DB, and now 2DB: done."
- `lessons/Live Sessions` June 13: "That's going to lead into a double break, sorry, a 2dB, which we're not
  interested in trading." June 24: "we already had a 2dB within 20 minutes of the market opening that's a sign it
  means that there's going to be a lot more manipulation ... it's been demoted to a paper trade for me".
- Jake (2026-10-07): "we don't trade 2DBs" is the overarching rule.

The only text that softens this is `lessons/Reversal Set Up.txt`: "previously if we got a 2DB, we would avoid that
setup. Now we're going to show you how to actually see which direction the market actually wants to go." The
video then uses the 2DB's reversal zone as *information* about which DB will be satisfied and says "This is once
again lower probability. So we would decrease our lot size". Jake's instruction overrides this; the amendment now
records it.

Corrected wording (rulebook §2.4): "Any 2DB on the setup timeframe of that index = SKIP, for the rest of that
session (Signal Legend: 'no other logic for a new set up should form after this point, until next session'). A 2DB
on the 1m voids 1m plays; the 5m may still set up ('You can get a 2 DB on the lower time frame on the one minute
and then you can avoid that setup and then you can actually wait to see if you get more confluence on the higher
time frame'). The 2DB's reversal zone may be read as information about which DB is more likely to complete and as
the next session's obligation; it is never an entry trigger." Delete the §3 downgrade and the "resolution" sentence
in §1 and live_rules §5; see §5 of this report for PLAYS.

Open point for Jake: `amendments.md` says "a reversal off a 2DB's white line is a separate Reversal Set Up play,
reduced size, not a 2DB trade". The Signal Legend's "no other logic for a new set up should form after this point,
until next session" would exclude even that in the same session. The amendment wording should say which.

### W2. live_rules §4: "Market Translator is valid on 15m, 5m, 1m; breaks down from 30m up."

Source, `Live Sessions` June 24 (answering a question about an M on the one-hour): "remember the strategy
specifically works on the 15 the 5 and the 1 it'll show you a setup on the 30 but again that's where it starts
breaking down Zeus works on daily 4 hour ... it's not designed to work on the one hour so remember you'll get false
readings if you look at it on any other time frame outside of the ones that was designed for".
`course/Market Translator.txt`: "You can actually see signals on the 30 second but we don't use that strategy just
because the fractals start to break apart the lower you go."

"The 30" is the 30-second chart, not 30 minutes. Corrected: "Market Translator is designed for 15m, 5m and 1m.
Signals print on the 30s but the fractal breaks down there (never run the strategy off a 30s signal). It is not
designed for 1h or above: signals there are false readings. Zeus covers daily / 4h / 15m."

### W3. rulebook §2.11 makes consolidation a hard SKIP: "More than 5-7 candles of consolidation at the zone, or wick-to-wick candles with no foothold."

Source treats 5+ candles at the 30s FVG as a power-of-three warning that changes the entry and stop, not a void:
`course/Market Translator.txt`: "Shouldn't take more than three to four candles to close like this ... If it starts
consolidating and you get five, six, seven candles in here, you could be getting a power of three ... So when you
get too much consolidation, what you want to do is wait for the market to close over the series of candles and
then give it one more candle to see if we get pulled back into the range or if we tap this line and actually close
under it as well. And then you can take your entry there with your stop loss ... or an even safer stop loss would
actually be here. Candle one of the three candle pattern that created the 30 second fair value gap."
`course/Spotlight Strategy.txt`: "you need at least five candles to constitute as a consolidation."

The "wick-to-wick, no foothold" half is supported (June 13: "if it doesn't give us a foothole entry, and it keeps
those candles tight, they're doing that for a reason"; July 16: "unless there's an actual foothold entry, a proper
fair value gap, we're not interested") but that is the absence of an FVG, i.e. no setup, not a consolidation count.

Corrected: "5+ candles at the 30s FVG = power-of-three risk: require one extra candle to close outside the range
after the closure over the series, and use the safer stop (candle 1 of the 30s FVG pattern). Repeated ripping
through the same FVG (two or three times) = consolidation: stay out (Night 7: 'it ripped through this five minute
once, twice. If it wants to do it a third time, remember that's not even something I think I want to be a part of')."
Keep "no FVG / wick-to-wick" as a must-have failure (no foothold = no setup).

### W4. rulebook §1 Spotlight: "Opening FVG (first 5m FVG of the session; NY's is shaded green)"

Source, `course/Spotlight Strategy.txt`: "every session has an opening fair value gap ... It's the first fair value
gap created on the five minute in the zone itself ... In this particular case, it's red just because the market was
moving down and it was created by a bearish fair value gap." Colour is by direction (green bullish, red bearish),
not by session. Corrected: "Opening FVG = first 5m FVG of the session inside the DR; green if bullish, red if
bearish."

### W5. rulebook §1: "Going into one [purple/blue zone]: take 50% and move stop to breakeven even short of 2R."

Source makes the stop roll the requirement and the partial optional. `Live Sessions` Night 7: "The purple and the
blue zones are where you either take profit or protect yourself at least. Make sure you roll your stops ... if it's
under two R and you want to get into one of these freebie plays, roll your stop. You don't have to close off your
position. You can let it ride." `lessons/Blue and Purple Zones.txt`: "if you hit it you roll your stop, take a
partial and/or use them as your TP." live_rules §10 already has the right version ("Under 2R you may roll to
breakeven without closing anything"). Corrected: "Going into a purple/blue zone before 2R: be safe (stop to
breakeven) by the time price reaches it; a partial is optional; the zone is a valid TP."

### W6. rulebook §1 "False [triangle] = M, DB, then M (no new information; stick with the DB; watch for a 2DB)" and live_rules §5 / PLAYS "false triangle"

No source defines a "false triangle" or the M, DB, M order. The triangle is defined once, as M + DB:
`course/Market Translator.txt`: "a triangle pattern. That's where you get an M in one direction and a DB in the
other direction ... an M in one direction and a double break in the opposite direction is still telling you the
exact same thing that market wants to continue in the direction of the double break." `lessons/Signal Legend.txt`:
"Triangle Model: an M below, then another M and a DB up top. Both point the same direction."
`lessons/Core Strategy Walkthrough.txt`: "The first M and the first DB are the important ones."
Note the SOP disagrees with the course on tone: `sop.txt` §03 "Triangle Pattern — M in one direction + DB in the
other. Conflicting signals. Use extreme caution." (source-internal conflict; the course and the Signal Legend both
treat it as agreeing signals).

Corrected: one "triangle" configuration (M, [M], DB): bias = DB direction; a later M after a DB is simply a second
M (retracement coming; if in a position, secure profits — see M5). Drop "false triangle".

### W7. PLAYS "M continuation": "single M signal, retracement and cascade in the M direction"

The M model has no retracement step; the retracement is the DB model's extra step. `reference/fractal_effects_
strategies.txt`: "M: M → OPPOSITE → 5M → TAP → 1M → TAP → 30S → TAP → CLOSE → ENTER" vs "DB: DB → RETRACE → SAME →
5M → ...". `course/Market Translator.txt`: "The only thing that changed is there was a retracement first" (on DB).
"The M direction" is also ambiguous (the trade goes opposite the fake move). Corrected description: "M: first 5m FVG
opposite the fake move, tapped; 1m FVG tapped; 30s FVG tapped; close over the series. Target: liquidity / zone /
the M reversal line."

### W8. rulebook §3 must-have: "first FVG at each step (one compromise max, e.g. 2nd FVG of a string)"

The compromise is never allowed on the 5m. `Live Sessions` Night 7: "The five minute is the one that I'm not
willing to waver on. I will always use the first presented fair value gap when it comes to the one minute and the
32nd. So 32nd, I'm a little bit more lenient. One minute, I try not to." July 16: "You're only allowed one
compromise. One compromise when it comes to the fair value gaps." Night 7 on the 30s: "I'll only take the first
two ... I don't care if there's a third and a fourth". live_rules §7 has this right; the rulebook must-have must
say "first presented 5m FVG, no exceptions; one compromise allowed on the 1m or 30s (second of a string, never a
third)".

### W9. rulebook §4: "Exit if it consolidates 10-15 minutes right after entry before it is safe." (also live_rules §10)

Not in any provided source. The closest rule is different: `course/Spotlight Strategy.txt` (higher-timeframe
reversal): "If the price stays in these gaps [4H/daily FVG or liquidity] too long and starts consolidating, this
indicates a loss of momentum ... it's often best to exit the trade at break even rather than waiting for the
expected extension." Corrected: "If price reaches a 4H/daily FVG or HTF liquidity and consolidates there before the
trade is safe, exit at breakeven." The "10-15 minutes" figure should be dropped unless it is in one of the 5
sessions not provided.

---

## 2. Contradictions inside the rules (rulebook.md vs live_rules.md vs rules_code.py vs prompts.py)

### C1. 2DB
- rulebook §2.4 "unresolved 2DB" / §3 "2DB resolved" / §5 "2DB" white line; live_rules §5 "see the rulebook for the
  newer reversal-zone resolution"; PLAYS "2DB: ... resolved by the reversal-zone rule";
  rules_code.py `hard_rules()` (01:44 version): `"§2.4 2DB: we don't trade 2DBs"` first; amendments.md: SKIP always.
- Source supports the code/amendment (W1). The three .md files and PLAYS still carry the old text and are what the
  model reads; DECISION_SYSTEM puts amendments first so the model should follow the amendment, but SCAN_SYSTEM only
  receives rulebook §5 onward (`scan_system()` slices from "## 5.") plus PLAYS, so the scanner never sees the
  amendment and can still report a "2DB" play.

### C2. prompts.py `decision_user()` vs amendments priority
`decision_user`: "the rulebook still wins on conflicts unless the passage is from the Reversal Set Up video".
`amendments.md`: "These override everything else." A retrieved Reversal Set Up passage ("Now we're going to show you
how to actually see which direction the market actually wants to go" on a 2DB) is told to win over the rulebook,
which now contradicts the amendment. The exception clause should be removed or made subordinate to amendments.

### C3. ND hard rule vs Spotlight-only setups
- rulebook §2.1: "No Market Translator signal armed it (trend-fallback / 'ND'). Never trade ND."
- live_rules §13: "The instructor will take a Spotlight setup alone (correction to older notes that said it needs
  an MT signal)."
- Source: the Spotlight/DR strategy is a complete standalone model (`sop.txt` §07 "DR STRATEGY", `course/Spotlight
  Strategy.txt`: "The strategy begins with a bullish or bearish confirmation signal providing a clear directional
  bias"). `sop.txt` §08: "No clear M or DB signal → flat is a position, no trade" is about MT signals only.
- Resolution: §2.1 should read "no MT signal AND no Spotlight confirmation". A Spotlight-only setup is a different
  play (see §5) with its own entry/stop/TP, not an "ND".

### C4. NY cutoff: 11:00 vs 11:30
- rulebook §2.3: "NY: no new entries after 11:00 ET ... Hard cutoff 11:30 ET for the NY session." (two cutoffs)
- rules_code.py: `hm >= (11, 0)` → SKIP.
- Course: "if we're not in a high probability trade setup by 11.30 Eastern Standard Time, then we forfeit that
  session" and "you would never take this just because again, the window of opportunity had already closed".
- Live (July 14): "Honestly, 10.30 to 11 is the latest I've ever stayed for a New York session" ... "I personally,
  I've never stayed past 11 o'clock Eastern Standard Time" ... "The reason we say two hours is because the session
  itself is still valid until the next session starts. But, rarely will you get a setup so late in the game."
- Live sessions win per the rulebook's own priority, so 11:00 is defensible, but the rulebook should state one
  number and label 11:00–11:30 as what it is in the source: valid but low-probability / demo ("I would take it in a
  demo just this late in the game", July 16).

### C5. Asia window: rulebook vs course vs code
- rulebook §2.3: "Asia: done by ~10 PM ET."
- Course (`Market Translator.txt`): "Asia starts at 8 o'clock Eastern Standard. So if you're not in a high
  probability trade setup by 11, you're pretty much out and done." (3 hours, conflicting with the "two hours after
  that session begins" rule stated in the same passage; probably a slip for 10.)
- rules_code.py: `if session == "asia" and (22, 0) <= hm` — an Asia entry between 00:00 and 02:00 ET has
  `hm < (22, 0)` and passes the window check. Bug: the Asia check must handle the post-midnight part of the session
  (e.g. `hm >= (22, 0) or hm < (2, 0)`).

### C6. Weekend: rules_code vs scanner
- rules_code.py: `if et.weekday() >= 5: "§2.3 weekend"` (Saturday and Sunday).
- scanner.py `in_window()`: `if et.weekday() == 5: return False` (Saturday only).
- Source: Asia opens 8 PM ET ("Asia starts at 8 o'clock Eastern Standard"); on Sunday evening that is a normal
  Asia session (index futures trade from Sunday 6 PM ET). The hard rule skips every Sunday-evening Asia setup as
  "weekend" while the scanner scans them. Pick one; the source supports Sunday-evening Asia being tradeable.

### C7. NY PM session has no rule
- Course: "we have the New York PM session here in purple. And again, each session has its own color coded signals."
  Live June 24: "I would have just came back for the PM session see uh what the signals are telling me there."
  Night 7: "you had a double break during the afternoon session".
- rulebook/live_rules: no PM window. rules_code.py: `session == "newyork" and hm >= (11, 0)` → every entry the
  engine labels "newyork" after 11:00 is skipped as "NY entry after 11:00 ET", which would mis-label PM-session
  setups; if the engine uses another label for the PM session, no window rule applies at all. The rulebook needs an
  explicit PM-session line (window unknown from the source: say so).

### C8. Reversal trades: rulebook §5 vs live_rules §5
- rulebook §5 (all reversal set ups allowed, reduced size) vs live_rules §5: "After a DB he stops looking for
  reversal setups" and "He prefers continuation over reversal. With bearish confirmations and DBs on all three
  indices it is 'a sell or nothing'."
- Source: July 14: "Right now, we just got a double break here. So, now, I'm done looking for that reversal setup.
  Even if it comes, I'm not going to take it." July 16: "I'm not looking to trade a reversal here. I was looking for
  a continuation. It's a sell or nothing for me. So if we do get a reversal setup, I'm not interested. We have
  bearish confirmations across all three of them and double breaks on all three of them." June 13: "I don't like to
  trade reversals."
- These are compatible if stated precisely: the Reversal Set Up requires the DB to have *failed* (criterion 2: body
  close through the DB's reversal area; criterion 3: reversal zone). While a DB / Spotlight confirmation on that
  index is intact, the directional filter (live_rules §3) applies and no reversal is taken. rulebook §5 should say
  so instead of "the video overrides the live rule".

### C9. Consolidation: three different treatments
rulebook §2.11 hard SKIP; live_rules §11 "more = indecisive market, use that index for divergence only"; course:
wait one more candle + safer stop (W3). The course version is the only one quoted verbatim in the source.

### C10. Zone partial: rulebook §1 "take 50% ... even short of 2R" vs live_rules §10 "Under 2R you may roll to breakeven without closing anything". Source supports live_rules (W5).

### C11. "Juice drunk": rulebook §2.12 is a hard SKIP ("and the setup is not complete on both indices") but the
matching size rule (live_rules §8: "require the full setup on both indices and use a reduced lot") is not in
rulebook §3 Downgrades, so the model has no path to grade it B/reduced. Source (June 23): "I need to see both of
these giving me the same setup ... and even then I'm going to go in with a reduced lot size". Add to Downgrades.

### C12. Priority chain claims that are not in the data
rulebook line 4: "(3) live_rules.md (rules pulled from the 12 live sessions)"; live_rules line 3: "Pulled from the
12 live-session transcripts". The file in `knowledge/lessons/` has 7. rulebook line 6: Reversal Set Up "(Oct 2026)".
Not supported (see header note).

---

## 3. Missing — rules the instructor states that are absent from rulebook/live_rules/code

### M1. Max two losses per session (hard stop; codeable from the decisions table)
`course/Money Managment.txt`: "Daily loss limit. Establish a daily loss limit to prevent significant drawdowns.
Once this limit is reached, stop trading for the day ... For example, in the DR strategy, we have two losses you can
take per each session. Anything more than that and you're technically gambling." `sop.txt` §08: "Already overtraded
the session → stop. Review tomorrow."

### M2. Fixed risk per trade
`sop.txt` §06: "Risk Management — Fixed % per trade. Never deviate." `course/Orientation.txt`: "So I'm risking 1% to
make 3%." The rules only say full/reduced; the base unit is never defined.

### M3. Divergence take-profit rule
`course/Market Translator.txt`: "Note regardless of whichever asset crosses your take profit threshold first, close
your position on the asset you're trading because this could be considered a delivery for both assets." `sop.txt`
§05: "If either asset hits TP threshold first → close your position on the asset you're trading." Not in §4
Management or live_rules §10.

### M4. 2DB scope and timeframe (see W1)
"until next session" (Signal Legend); "move on to another asset entirely or we wait for the next session"; 1m 2DB
voids the 1m only (course). Neither the amendment nor the code says for how long or on which timeframe the skip
holds.

### M5. 2M handling is incomplete (rulebook §1, PLAYS "2M return")
- Trade INTO the untouched FVG in the second M's direction is itself a play: `course/Market Translator.txt`: "So you
  could either look for a setup to go short right into here or you can wait for the market to come back here and
  then still look to fulfill that first setup."
- The return-then-continue is conditional on no HTF FVG having been hit: "look for a potential setup to go long if
  you didn't actually get an entry and you haven't hit a higher time frame, four hour or daily fair value gap up
  here."
- Management when the 2nd M prints while in a trade: `lessons/Core Strategy Walkthrough.txt`: "If I'm already in a
  setup and get a second M, secure profits, roll stops, protect."

### M6. M model and the golden rule stated explicitly
`reference/fractal_effects_strategies.txt`: "THE 5M FVG MUST BE TAPPED. No tap = no trade." ... "the golden rule:
If ANY step doesn't happen, there is NO entry." The rulebook never writes out the M sequence (first 5m FVG opposite
the fake move → tap → first 1m FVG → tap → first 30s FVG → tap → close over the series). The engine enforces the
cascade, but the model grades "must-haves" without the list.

### M7. Spotlight (DR) play as a standalone model
`sop.txt` §07 and `course/Spotlight Strategy.txt`: setup 5m confirmation → "retrace back into the dealing range ...
tap a fair value gap and most likely the 20 EMA" (+ Fib 61–79%) → "drop down into the one minute timeframe and look
for a creation of a one minute fair value gap ... retrace back to this fair value gap and create an engulfing candle
and then a 30 second fair value gap" → entry on closure. Stop: "set to ticks ... above or below the rejecting
candle." Target: "aim for at least one [standard deviation] ... 1, maybe even 1.5"; "if it's more than 1 to 3, then
proceed with caution." Window: "If no setup is identified within one hour after the range formation, consider
passing on trading for that session" (NY: 10:25 → 11:25). Checklist: "Signal must align with 4H session model
before entry." None of this is in the rules or PLAYS; rulebook §2.1 would skip it as ND (C3).

### M8. 4-hour model rules (HTF Analysis course, SOP §02)
`course/HTF Analysis.txt`: "And 10-11. If 10am manipulates, avoid entries. Price may reverse off of a higher time
frame PD array, i.e. a 4-hour fair value gap or liquidity sweep, even if the Blue Zone has a double break. Still
avoid." `sop.txt` §08: "10–11 AM session manipulates → avoid (HTF reversal risk)". Also: "it's only a buy model
until it's not ... once we've actually accomplished that goal and we've hit that higher time frame PDA rate, we
could reverse." Only the second idea is in the rules (§2.12, live_rules §5). The 10–11 AM manipulation rule is
absent; it is partly checkable (does the 10:00 4H candle sweep a high/low or tap a 4H FVG?).

### M9. Entry confirmation nuances (course, Market Translator)
"if you have a fair value gap that was left [on the push out], there are chances that this one will also be hit ...
So that's why we always give it maybe one more candle to see, are we going to close back into the range and tap that
fair value gap, or are we going to close outside the range just to be safe?" and "since we went much deeper and we
actually went back to the one minute, I would have actually waited for another candle to close outside the range."
Plus the V-shape requirement: "we want to see a nice V shape closure. Shouldn't take more than three to four candles."
Also, a closure must be strictly beyond the line: July 16: "Even if it's one pip higher, that constitutes as a
closure ... Just getting to the same exact point does not constitute as a break."

### M10. DB retracement completion has three parts in the source; the rulebook keeps one and demotes another to a booster
`lessons/Core Strategy Walkthrough.txt`: "The retracement is done when: (1) we get a pullback into the range and hit
a FVG in the DB leg ... or if there is no FVG, the market pulls back and maybe touches the midpoint of the double
break candle; (2) an immediate rebalance: one candle up, one candle down, an engulfing candle; (3) a fair value gap
created in the direction of the double break: the five minute FVG." `course/Market Translator.txt` adds the quality
tell: "you get a fair value gap in the leg that pushed back into the zone and then you push back out of it ...
you create one and then you disrespect it showing that the market actually does want to push down. ... And then
secondly, we hit one of our key zones." rulebook §3 lists "Immediate rebalance (engulfing candle) at the zone" as a
booster only, and the "FVG left on the retracement leg then disrespected" tell is absent.

### M11. 1m-play target and timeframe discipline (rulebook §4/§5 silent; live_rules §4 partial)
`course/Market Translator.txt`: "our take profit should be most of the time the double break top because as soon
as we cross that line, it's actually going to create a double break on the higher time frame on the five minute".
July 16: "If you have a double break on the five minute, you want to stick to the five minute ... The higher
probability is off of the bigger structure. So always stick to whatever timeframe you're on."

### M12. Directional filter as a hard rule in the rulebook
live_rules §3 has it ("A DB or Spotlight confirmation one way means that index can only be traded that way") but
rulebook §2 does not list it as a hard rule. Source: `course/Market Translator.txt` on DB: "Either we trade in that
direction or we don't trade that asset." July 16: "Can't buy NES, right? We have a double break to the downside."
Spotlight: "we're only looking for a retracement back into our range and then an extension" after confirmation.

### M13. Sessions: NY PM and Sunday Asia (see C6, C7).

### M14. Consolidation at a higher-timeframe level after entry → exit at breakeven (the real source of the §4 rule; see W9).

### M15. Consequence-encroachment kill condition
`course/Market Dynamics.txt`: "If you are bearish, you don't want any candles to close above the consequence
encroachment of the fair value gap. And if you are bullish, you don't want candles to close below the consequence
encroachment ... if it closes over this midpoint, there is a cause for concern as price might not respect this
particular fair value gap." Useful for the `kill_conditions` field; absent from the rules.

### M16. Power-of-three vs signal
`course/Spotlight Strategy.txt`: "you can get a signal down here. So you get consolidation and a signal here, but we
know that the market most likely wants to go in the opposite direction ... You don't want to pair a signal against
power of three." A signal printed on the breakout of a 5+ candle consolidation is suspect. Absent.

### M17. Minor, for completeness
- "True" DB candle colour (`course/HTF Analysis.txt`, blue-zone strategy): "a true double break has to be the same
  color as the initial candle that broke the range." Applies to range breaks the trader marks by hand; the MT paints
  its own DBs, so low weight.
- Friday: `course/Weekly Framework.txt`: "They call it Trap Friday for a reason. It does a lot of manipulation so
  proceed with caution ... anticipate a retracement of approximately 20 to 30% of the weekly candle" after an HTF
  level is hit. Absent.
- Zone-less markets: `course/Spotlight Strategy.txt`: "we're at all time highs, right? There's no liquidity up here.
  You can reverse it any time". live_rules §10 has a version; rulebook does not.

---

## 4. Priority of hard rules (from the source)

The SOP's own structure is the best guide: §08 "HARD STOPS (Do Not Trade)" lists, in order, high-impact news
(CPI/PPI/NFP/FOMC/Fed Chair speech), then "Immediate Stop Conditions": 2DB, 10–11 AM manipulation, no clear M or DB
signal, RRR below 1:3, already overtraded. The pre-session checklist (§09) puts the calendar first ("CPI/PPI/NFP/FOMC
today? If yes → DO NOT TRADE"), then bias, then the 4H model; the pre-trigger checklist puts "M or DB signal
confirmed on correct TF?" then "is it voided by 2DB?" then the cascade, then Fib/EMA, then RRR.

Proposed reporting order (first fired = the stated reason; all fired reasons kept, as `hard_rules()` now does):

Tier 0 — day-level, absolute, decided before any signal is read
1. High-impact news day for the asset / live Fed-Chair or presidential speech in progress. Spotlight course: "We
   abstain from trading on days marked by high impact news for the specific asset." July 14: "the reason we don't
   trade these days is because all strategies go out the window. They use these days to reprice ... Never try to
   bend your strategy to fit what's happening during these days." A DB printed on a news candle is void ("this was a
   news candle ... I don't interpret it at all"). CPI/PPI week and pre-news nights: demo only (July 14: "pretty much
   on CPI and PPI. You're already sidelined"; Night 7: "these are good days to practice").
2. Session loss limit reached (two losses) / overtraded (M1).

Tier 1 — signal-level, absolute, "overarching" (Jake: 2DB)
3. 2DB on the setup timeframe of that index (W1). Jake names this the overarching rule; the code already reports it
   first. Ordering 2DB before news is acceptable because both are absolute; what matters is that neither is ever
   reported as "window".
4. No signal at all (ND / trend-fallback) and no Spotlight confirmation: "flat is a position, no trade" (SOP).
5. Spotlight false day on that index: "We stop trading when this happens ... That's a completely void."
6. Trading against that index's DB / Spotlight confirmation (directional filter, M12): "Either we trade in that
   direction or we don't trade that asset."

Tier 2 — setup-level, absolute
7. Any cascade step missing: "If ANY step doesn't happen, there is NO entry" — includes DB with no retracement /
   runaway ("A DB with no retracement is a runaway: no foothold, no trade") and no first-presented FVG.
8. RRR < 1:3 to a real target before the next obstacle: "Minimum 1:3. No exceptions." (SOP); "it did not give me the
   1 to 3 risk to reward ratio I was looking for, so I passed on it" (Money Management).
9. Entering deeper into / against a 4H-daily FVG or HTF liquidity already delivered (10–11 AM manipulation rule;
   "I'm not going to take this into or deeper into a four hour fair value gap"; "juice drunk" without both indices
   complete).

Tier 3 — secondary (downgrade first, skip only at the hard edge)
10. Session window. The source describes it as probability decay, not a void, until the hard edge: "the probabilities
    decrease the further we go into that window of opportunity"; "I would take it in a demo just this late in the
    game"; hard edge "by 11.30 ... we forfeit that session". The code's 11:00 cutoff is the live-session practice.
11. Divergence (buying the weaker / selling the stronger), outside-the-range start, late in session, second-FVG
    compromise: reduced size, not skip ("Divergence alone doesn't mean anything").

---

## 5. Plays list check (`app/prompts.py` PLAYS)

| Key | Verdict | Note |
|---|---|---|
| DB continuation | OK | Add: entry under the DB, be safe by the DB high; "Ideally 2R is right around the DB high". |
| M continuation | Wrong description (W7) | No retracement step; rename "M (manipulation) set up". |
| 2M return | Incomplete (M5) | Two variants: trade INTO the untouched FVG (2nd-M direction) or wait for the tap then trade the 1st-M direction (only if no HTF FVG hit). |
| true triangle | Rename | Source has one "triangle" (M, [M], DB). |
| false triangle | Unsourced (W6) | Remove. |
| 2DB | Wrong (W1) | Not a play. Keep only as a skip label: "2DB — never traded". SCAN_SYSTEM receives PLAYS and could report it as a forming setup. |
| reversal set up | OK | Criteria match the video; add the directional-filter condition (C8) and the amendment's 2DB wording. |
| M via reversal zone | OK | Video: "you can use that reversal zone to continue for the M setup". |
| 1m play | OK | Add target = the 5m DB high (M11) and "only off a 1m M or 1m DB; never off a 30s signal" (W2). |
| blue/purple zone play | OK | July 16: "we're going to call that the blue zone play ... Make sure the setup is there, the one minute fair value gap, the 30 second tap, the signal, everything." |
| other | OK | |

Missing plays:
- **Spotlight (DR) play** — M7. The engine never arms it, so it belongs in SCAN_SYSTEM's list as well.
- **DB into a 5m FVG (1m DB against a 5m M after an HTF level)** — `lessons/Invalidations and Reversals.txt`: "we can
  only take a setup INTO the five-minute FVG: take the DB retracement entry, but be in a safe trade ... by the time we
  tap the five-minute FVG." rulebook §5 describes it but PLAYS has no label for it; it is a DB-continuation variant with
  a forced target.
- **Trade TO a zone** (`sop.txt` §05: "If manipulation is away from zone and zone aligns with daily bias → enter using
  5M FVG entry toward the zone") is the M play with the zone as target; a label is optional.
- Zeus (daily/4H/15m) plays are out of scope for the 5m engine; not needed.

---

## 6. Vague / untestable — flag so the agent says "unknown" rather than pretending

From the engine data (fvg-mcp) and a screenshot the following cannot be verified reliably:

- 4H / daily FVG location and whether HTF liquidity was swept (rulebook §2.7, §2.8, §5 criterion 1, M8, "juice
  drunk"). Vision reads 5m/1m windows only.
- Spotlight false day, DR box, confirmation, opening FVG, trend table, EMAs: vision-only; often off-screen or on a
  forming candle.
- Reversal zones and white-line body closes: vision-only; the engine has no field for them.
- Divergence / majority rules: the engine tracks `SYMBOLS` = MNQ, MES by default; "2 of 3 indices (NQ, ES, YM)" cannot
  be evaluated without YM, and "stronger/weaker pair" needs both charts at the same moment.
- Consolidation candle counts, V-shape, "wick-to-wick", "immediate rebalance": vision-only and timeframe dependent.
- Live speeches not on the economic calendar (July 16: "Trump speaking at 6 p.m. I'm surprised that's not red
  folder"): `news_rule()` only sees calendar rows. Say "unknown" unless the calendar lists it.
- 10–11 AM manipulation (M8): needs the 4H candle; not in the engine.
- Whether the index is "telling the most consistent story", "sloppy morning", "when in doubt demote": judgment calls.
- Session window edge cases: NY PM session, Sunday-evening Asia (C6/C7).

live_rules.md items not found in the 7 provided sessions (may come from the 5 missing ones; treat as unverified, do
not cite them as instructor rules until the transcripts are added):
- §2 "After-hours earnings (e.g. AMD) can move NAS."
- §3 "Majority rules: if two of three indices have a 5m DB up, he won't sell anything that day." (also rulebook §2.9).
  The provided sessions show a per-index filter and "sell or nothing" when all three agree, not a 2-of-3 rule.
- §3 "A signal-less index can be the tiebreaker."
- §6 "Retracement zone: any FVG inside the DB leg, plus an FVG in the one candle to the right of the DB candle."
  (Signal Legend/Core walkthrough support "FVG in the DB leg, else beneath / midpoint of the DB candle"; the "one
  candle to the right" extension is unverified.)
- §9 "Before an expected higher-timeframe DB into all-time highs, secure a partial or move the stop to the midpoint."
- §10 "align 2R with a liquidity level when possible (1.96R is fine)"; "Exit if it consolidates 10-15 minutes right
  after entry" (W9); "Exit at breakeven if price breaks a protected low after power of three already happened."
- §11 "Normal consolidation is 5-7 candles; more = indecisive market, use that index for divergence only."
- §14 "A DB straight into a 4H FVG ... drop the index if it closes back below."

Source-internal conflicts the rules should not try to resolve silently:
- Breakeven trigger: `sop.txt` "At 50% TP hit → move SL to breakeven" vs course/live "as soon as we get to 2R, I would
  have closed off 50% of my position and then rolled my stop loss to break even". Rulebook follows the course (fine);
  note the SOP differs.
- Triangle: SOP "Conflicting signals. Use extreme caution" vs course "still telling you the exact same thing" (W6).
- Asia cutoff: course "by 11" vs its own two-hour rule (C5).
- News: HTF Analysis "News doesn't change the model. It accelerates it" (4H structure reading) vs Spotlight/SOP "do
  not trade" (entries). Both hold: read structure, take no entries.
- Stops: course preliminary/definitive stop vs July 16 "I've actually even gotten rid of the whole preliminary and
  definitive stop losses ... the high low of the 30 second fair value gap leg. That is our definitive stop loss now."
  rulebook §4 follows the live version (correct).
