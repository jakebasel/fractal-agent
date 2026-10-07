# fractal-agent

Paper-only AI review layer for the Fractal Effects strategy. Watches fvg-mcp's entries on
MNQ1!/MES1!, reads a live TradingView screenshot with a cheap vision model, has DeepSeek
(via OpenRouter) decide TAKE/SKIP against the rulebook in `rules/`, logs everything to
SQLite/CSV, settles each row with fvg-mcp's scored result, and writes a lesson per trade.

Start with **HANDOFF.md**.
