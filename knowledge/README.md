# knowledge/ — the full material the agent searches

Every `.txt` / `.md` file in here is indexed automatically at start-up (BM25, `app/knowledge.py`).
For each setup the 6 most relevant passages go into DeepSeek's prompt next to the rulebook.
To add material: drop a text file in the right folder and redeploy. Nothing else to change.

- `course/` — the 9 course video transcripts (Orientation, Market Dynamics, HTF Analysis,
  Market Translator, Zeus, Spotlight, Weekly Framework, Money Management, Mindset).
  Source: Jake's Mac, `~/Downloads/trading/`.
- `lessons/` — mini lessons: Core Strategy Walkthrough, Invalidations & Reversals, Divergence,
  Blue & Purple Zones, Signal Legend, Reversal Set Up (Oct 2026, newest).
- `reference/` — text of the SOP cheat sheet and "Fractal Effects Strategies" PDF.
  `reference/images/` — chart-style reference images (Market Translator screenshots PDF and
  the chart-settings PDF), not yet sent to the vision model.

Not in here yet: the raw live-session transcripts (12 sessions, ~440 KB, mostly filler). Their
rules are distilled in `rules/live_rules.md`. The raw file lives in the claude.ai "Trading"
project as `live trading trasnscript.txt` — download it and drop it in `lessons/` if wanted;
the indexer strips repeated filler lines.
