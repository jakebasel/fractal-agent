# Working agreements — fractal-agent

Read HANDOFF.md first.

- **Paper only.** No order placement, modification or cancellation code in this repo unless Jake
  explicitly asks for live execution.
- **fvg-mcp is read-only from here.** Only call its MCP tools; never POST to its admin/settings.
- **Push to `main` deploys** (once the Coolify app exists). Run `tests/test_agent.py` before
  every push; never leave main broken.
- **Times shown to humans are ET**; storage is UTC ISO.
- **Rule changes come from the source.** `rules/` reflects the Fractal Effects course, the live
  sessions and the Reversal Set Up video. Lessons may *propose* changes; only Jake approves them
  into `rules/amendments.md`.
- **Every results table carries n, win%, avgR, total R and max drawdown**, and says the window.
- **Hypotheses are compared on the same trades.** A proposed change is judged by its shadow
  book vs the agent vs the core strategy on identical settled entries, never on different windows.
- **Approving a hypothesis = Jake clicks Approve, then the rule is committed to
  `rules/amendments.md`** (that bumps `rules_version`). Never edit amendments.md on a proposal alone.
- Jake wants plain language, short answers, bottom line first.
