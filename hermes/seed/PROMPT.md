Review the settled paper trades waiting for you. Steps, no questions asked (there is no human):
1. Call the paper MCP tool review_queue with reviewer "hermes" and limit 3.
2. For each trade: read everything it carries; if a chart detail would decide the call, ask
   chart_question(entry_id, "<specific question>", at="decision") (and at="exit" for exit notes).
   Compare the decision with the result (r) and with managed_r. Decide the verdict.
3. Post each review with: bin/post_review.sh '<json>'  (the JSON shape is in AGENTS.md).
4. Update your memory with any pattern worth tracking across trades; patch the trading-review
   skill if you found a reusable check.
5. Finish with a 5-line summary: trades reviewed, verdicts, proposals filed.
Keep it under 40 tool calls. If the queue is empty, say so and stop.
