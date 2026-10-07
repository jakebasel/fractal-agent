---
name: trading-review
description: Review settled Fractal Effects paper trades (wins and losses) for what the chart, sister index, FVGs or 4H targets should have changed; post reviews and testable proposals
version: 0.1.0
---
## When to Use
Every run: the paper agent's review_queue has settled trades without a hermes review.

## Procedure
1. review_queue(reviewer="hermes", limit=3).
   Classify: taken+lost (why not skipped?), skipped+won (why skipped?), taken+won and
   skipped+lost (what made it right). The goal is the optimal take/skip line and the exit.
2. Per trade, check in this order: (a) hard rules and must-haves vs what the engine and the
   chart read show; (b) the sister index (MES for MNQ, MNQ for MES): stronger/weaker, a DB the
   other way, same idea on both; (c) 4H/daily FVGs and liquidity in the trade's path (htf_fvgs,
   targets); (d) blue/purple zones and Spotlight (chart_read, chart_question); (e) the exit: was
   the trade safe by the obstacle, did a 5m DB against print (managed_r), partial at 2R or zone.
3. Verdict: a rule-following loss is still right_take; wrong_* only when the evidence was there.
4. bin/post_review.sh with the JSON; propose only a testable IF/THEN rule the rulebook lacks.
5. Memory: keep a short running list of patterns (what keeps deciding wins vs losses).

## Pitfalls
- Do not invent chart details: use chart_read and chart_question; say "not visible" otherwise.
- One trade is weak evidence; do not over-generalise.
- Never try to change rules directly; only reviews and proposals.

## Verification
post_review.sh prints the HTTP code: 200 means filed. reviews(limit=3) shows it.
