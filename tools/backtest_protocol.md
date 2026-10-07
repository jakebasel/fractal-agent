# Backtest protocol (how a tweak earns its way into the rules)

The core strategy stays as it is. A "tweak" is one filter or one size rule on top of it, written
as `IF <something the data carries> THEN SKIP | reduce size`. This protocol exists so that a
tweak that looks good is actually good, not just lucky on the trades we happened to look at.

1. **Pre-register.** Write the tweak down first, as a filter over ledger columns (see the DSL in
   `tools/backtest.py`). What counts as a pass is fixed in advance (below). No looking at the
   result and then editing the tweak.
2. **Split the data by time.** The ledger is cut at a fixed date into a *train* half and a
   *holdout* half. A tweak is evaluated on train; the holdout number is only read once, when the
   tweak passes train. Every ledger pull moves the cut forward, so the holdout is always the
   most recent data the tweak never saw.
3. **Same trades, same management.** The tweak is compared with the code-rules book on the
   identical trades (it can only remove or resize trades), scored the way fvg-mcp scores
   (2R + runner to 3R). Chart-dependent rules cannot be backtested here; they go through the
   live shadow test instead.
4. **Pass = all of:** at least 30 trades affected on train (the "30 trades per parameter" rule);
   total R improves on train AND on holdout; the holdout keeps at least half of the train edge
   per trade (a >50% in-sample→out-of-sample drop is the standard overfitting red flag); max
   drawdown not deeper on either; the trades it removes have negative average R on both halves
   (it is cutting losers, not just cutting). One or two miss: "inconclusive", keep collecting.
   Three or more miss: "fail". A PASS also has to clear the multiple-testing bar (below).
5. **Every run is logged** to `reports/backtest_log.jsonl` with the tweak text, the data cut and
   the numbers. The number of tweaks tried is part of the evidence: if 20 were tried and one
   passed, that one is probably noise. The code applies a multiple-testing bar: with k tweaks
   tried so far, a PASS must beat the base book on holdout by more than (max drawdown / 4) ×
   log2(k+1) R, otherwise it is marked "PASS (below multiple-testing bar)".
6. **One tweak at a time.** Tweaks are stacked only after each passed alone, and the stack is
   re-run as a whole.
7. **Then the live shadow test.** A passed tweak becomes a hypothesis on the dashboard and runs
   on new trades (`MIN_N_FOR_VERDICT`) before Jake approves it into `rules/amendments.md`.

What DeepSeek is for in this loop: proposing tweaks in the DSL from the breakdown tables and the
rulebook (`tools/backtest.py --propose`, ~1 cent per round), and writing the plain-language
reading of a result. It never decides a pass: the pass rule is code.
