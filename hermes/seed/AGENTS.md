# Trading review: how to work
- Tools: the `paper` MCP server (review_queue = compact per-trade packets; decision_detail = the
  full record; chart_question; rules_text; knowledge_search = course + live-session passages;
  strategy_report; backtest_report; spotted_setups = the chart scanner's finds; lessons;
  hypotheses; reviews; paper_stats) and the `fvg` MCP server (entries, setups, recent_events =
  the Market Translator alert stream from TradingView, archived_prices = the price tape,
  confluence = active FVGs + latest signals). Both are read-only.
- Cost discipline: the review_queue packet is enough for most reviews; call decision_detail,
  recent_events or archived_prices only when a specific question needs them, and never paste
  raw tick tapes or long event lists into your reasoning: summarise them to the few numbers you
  need. Download a screenshot only when a chart detail decides the call.
- Evidence priority on a conflict: amendments > rulebook > live-session rules > course
  passages > the decider's notes. rules_text(section) returns the rule files; knowledge_search
  (query) returns the most relevant course / live-session passages.
- Writing back: ONLY through the two scripts in ./bin (they POST to the paper agent). ALWAYS
  write the JSON to a file first with the file tool (e.g. ./reviews/<entry_id>.json), then run
  `bin/post_review.sh ./reviews/<entry_id>.json` (same for `bin/propose.sh <file>`). Never put the
  JSON inline on the command line: shell quoting mangles it (escaped quotes = invalid JSON = 400).
  The script prints the server reply and "HTTP 200" when filed; "INVALID JSON" means fix the file.
- Seeing the chart: `bin/get_shot.sh <screenshot name>` downloads it to ./shots/<name> (names come
  from decision_detail / review_queue `screenshots.at_decision` and `.at_exit`; the left window
  is the 5-minute charts, the right the 1-minute; MNQ and MES both visible); then use the vision
  tool on the file. Or chart_question(entry_id, question, at) for a targeted read.
- `review_queue(reviewer="hermes", limit=2)` gives everything settled you have not reviewed:
  engine trades (kind engine_trade, key entry_id) and scored scanner setups (kind scanner_setup,
  key scan_id: plays the engine never armed, scored on the tape; review them for whether the
  strategy should have been looking there). Post a scanner review with "scan_id" instead of
  "entry_id". Also: pending_setups (what the engine is arming right now), instructor_calls (the
  instructor's own skips and rules from the live sessions, with quotes), spotted_setups.
  Each engine trade packet has:
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
