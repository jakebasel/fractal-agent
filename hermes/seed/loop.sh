#!/bin/bash
# Seeds /opt/data on first run, then every REVIEW_EVERY_MIN minutes: if the paper agent has
# settled trades that Hermes has not reviewed, run one headless Hermes session on them.
# No queue = no LLM call = no cost.
set -u
SEED=/opt/seed; DATA=/opt/data
mkdir -p "$DATA/trading-review/bin" "$DATA/skills/trading-review" "$DATA/skills-agent" "$DATA/memories"
[ -f "$DATA/config.yaml" ] || cp "$SEED/config.yaml" "$DATA/config.yaml"
cp "$SEED/SOUL.md" "$DATA/SOUL.md"
cp "$SEED/AGENTS.md" "$DATA/trading-review/AGENTS.md"
cp "$SEED/PROMPT.md" "$DATA/trading-review/PROMPT.md"
cp "$SEED/skills/trading-review/SKILL.md" "$DATA/skills/trading-review/SKILL.md"
cp "$SEED"/bin/*.sh "$DATA/trading-review/bin/"; chmod 700 "$DATA"/trading-review/bin/*.sh
printf 'AGENT_TOKEN=%s\n' "${AGENT_TOKEN:-}" > "$DATA/trading-review/.token"; chmod 600 "$DATA/trading-review/.token"
echo "[hermes-loop] seeded; reviewing every ${REVIEW_EVERY_MIN:-20} min" 
while true; do
  n=$(curl -sS -m 30 -H "X-Agent-Token: ${AGENT_TOKEN:-}" "${AGENT_URL:-https://agent.motivationpro.tech}/api/review_queue?reviewer=hermes&limit=3" | python3 -c 'import sys,json
try: print(len(json.load(sys.stdin)))
except Exception: print(0)' 2>/dev/null || echo 0)
  if [ "${n:-0}" -gt 0 ]; then
    echo "[hermes-loop] $(date -u +%FT%TZ) $n trade(s) to review"
    timeout 1500 hermes chat --query-file "$DATA/trading-review/PROMPT.md" --oneshot -Q \
      -t terminal,file,memory,skills,mcp-fvg,mcp-paper -s trading-review \
      --max-turns 40 --source trading-review 2>&1 | tail -40
  fi
  sleep $(( ${REVIEW_EVERY_MIN:-20} * 60 ))
done
