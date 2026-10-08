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

Live sessions:
- `lessons/Live Sessions (raw transcripts).txt` — the 12 June/July 2025 sessions (raw).
- `lessons/Live Session YYYY-MM-DD <title>.txt` — one file per session from Oct 2026 on, instructor
  lines only. Source: Jake's Wispr Flow recordings, pulled in with the `/live-session` skill
  (`.claude/skills/live-session/SKILL.md`): it files the transcript, labels his calls in
  `labels/instructor_calls_<mon>_<year>.json` (served by the `instructor_calls` MCP tool) and adds
  new rules to `rules/live_rules.md`. `wispr_ingested.json` lists what has been pulled.
  Their rules are distilled in `rules/live_rules.md`.
