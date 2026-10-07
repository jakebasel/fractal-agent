# Trading review: how to work
- Tools: the `paper` MCP server (review_queue, decision_detail, chart_question, strategy_report,
  lessons, hypotheses, reviews) and the `fvg` MCP server (entries, setups, recent_events,
  archived_prices, confluence). Both are read-only.
- Writing back: ONLY through the two scripts in ./bin (they POST to the paper agent):
  `bin/post_review.sh '<json>'` and `bin/propose.sh '<json>'`.
- `review_queue(reviewer="hermes", limit=3)` gives settled trades you have not reviewed. Each has:
  engine data (entry/stop/target, signal, retracement), `chart_read` (what the vision model saw:
  white lines, reversal zones, blue/purple zones, Spotlight, EMAs, trend table), `htf_fvgs` (4H and
  daily gaps with the entry's position), `_read` (spotlight / sister pair / targets as judged at
  the time), `_plan` (management plan), `r` (mechanical result), `managed_r` (result with the
  instructor's management rules), `reeval`, `screenshots` (names; use chart_question(entry_id,
  question, at="decision"|"exit") to ask the vision model about the saved image).
- A review JSON: {"entry_id": N, "reviewer": "hermes", "verdict": "right_take|wrong_take|right_skip|wrong_skip",
  "summary": "what should have decided take/skip (2-3 sentences, concrete)",
  "exit_notes": "how the exit/partials should have been handled given the chart (1-2 sentences)",
  "proposal": "IF <condition visible in the data> THEN <TAKE|SKIP|reduce size|exit rule>", or null,
  "proposal_title": "3-6 words", "rule_ref": "§x.y or null"}
- Do not propose what the rulebook already says; propose only when this trade clearly exposes a
  gap. One trade is weak evidence: say so in the summary when it is.
- After the reviews, update your memory with the patterns you are tracking (max a few lines) and
  patch the trading-review skill if you learned a reusable check.
