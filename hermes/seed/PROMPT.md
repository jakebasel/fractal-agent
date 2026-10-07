Review the settled paper trades waiting for you (there is no human in the loop; never ask).

1. review_queue(reviewer="hermes", limit=3) on the paper MCP server.
2. For EACH trade, work the two decision points:
   TAKE/SKIP: was the decision right given the core strategy and the evidence? Check the hard
   rules and must-haves against the engine data and chart_read; the sister index
   (pair_setups / pair_mt_recent and the _read.sister_pair note); htf_fvgs and the targets; the
   zones and Spotlight (chart_read; ask chart_question(entry_id, "<specific question>",
   at="decision") when a chart detail decides it); the session and news. If the rulebook or the
   course material speaks to the situation, look it up with rules_text / knowledge_search and
   cite it.
   EXIT/PROTECTION: compare r (mechanical 2R + runner) with managed_r (instructor's management
   rules) and the _plan the decider wrote; use chart_question(..., at="exit") to see the chart
   at the result; say where the partial, the breakeven roll and the exit should have been.
3. Post each review with bin/post_review.sh '<json>' (shape in AGENTS.md). Verdict rules: a
   rule-following loss is right_take; a skip that avoided a loss is right_skip; wrong_* only
   when the evidence to decide otherwise was available at the time.
4. Propose at most one IF/THEN rule per trade, only if this trade exposes a gap the rulebook
   (with amendments) does not cover; one trade is weak evidence and you say so.
5. Memory: keep a running list (a few lines) of the patterns deciding wins vs losses on the
   two decision points; patch the trading-review skill when you find a reusable check.
6. Finish with a 5-line summary: trades reviewed, verdicts, proposals filed, pattern watched.
Keep it under 40 tool calls. If the queue is empty, say so and stop.
