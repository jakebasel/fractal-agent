#!/bin/bash
# Seeds /opt/data on first run, then every REVIEW_EVERY_MIN minutes: if the paper agent has
# settled trades that Hermes has not reviewed, run one headless Hermes session on them.
# No queue = no LLM call = no cost.
set -u
SEED=/opt/seed; DATA=/opt/data
mkdir -p "$DATA/trading-review/bin" "$DATA/skills/trading-review" "$DATA/skills-agent" "$DATA/memories"
cp "$SEED/config.yaml" "$DATA/config.yaml"   # config is ours and versioned; memory/skills/sessions persist on the volume
cp "$SEED/SOUL.md" "$DATA/SOUL.md"
cp "$SEED/AGENTS.md" "$DATA/trading-review/AGENTS.md"
cp "$SEED/PROMPT.md" "$DATA/trading-review/PROMPT.md"
cp "$SEED/skills/trading-review/SKILL.md" "$DATA/skills/trading-review/SKILL.md"
cp "$SEED"/bin/*.sh "$DATA/trading-review/bin/"; chmod 700 "$DATA"/trading-review/bin/*.sh
printf 'AGENT_TOKEN=%s\n' "${AGENT_TOKEN:-}" > "$DATA/trading-review/.token"; chmod 600 "$DATA/trading-review/.token"
echo "[hermes-loop] seeded; reviewing every ${REVIEW_EVERY_MIN:-20} min"
while true; do
  resp=$(curl -sS -m 30 -H "X-Agent-Token: ${AGENT_TOKEN:-}" "${AGENT_URL:-https://agent.motivationpro.tech}/api/review_queue?reviewer=hermes&limit=2" 2>&1)
  n=$(printf '%s' "$resp" | python3 -c 'import sys,json
try: print(len(json.load(sys.stdin)))
except Exception as e: print(0)' 2>/dev/null)
  n=${n:-0}
  echo "[hermes-loop] $(date -u +%FT%TZ) queue=$n $( [ "$n" = 0 ] && printf '%s' "$resp" | head -c 120 )"
  if [ "$n" -gt 0 ] 2>/dev/null; then
    # --yolo: no approval prompts (headless; the container holds only the agent token). The
    # MCP toolsets come from config.yaml. -Q = programmatic mode (without it the run hangs).
    # Output streams line by line to the container log and to runs.log on the volume.
    # --format stream-json: one JSON event per line as it happens (tool calls, results, text),
    # so the container log shows progress instead of only the final answer
    timeout 900 hermes chat --query-file "$DATA/trading-review/PROMPT.md" --oneshot -Q --yolo \
      --format stream-json -s trading-review --max-turns 30 --source trading-review 2>&1 \
      | tee -a "$DATA/trading-review/runs.log" \
      | python3 -u -c '
import sys, json
for line in sys.stdin:
    line = line.rstrip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except ValueError:
        print(line[:220]); continue
    t = e.get("type") or e.get("event") or ""
    name = e.get("name") or e.get("tool") or (e.get("tool_call") or {}).get("name") or ""
    if "result" in t:
        print(f"[{t}] {name} " + json.dumps(e)[:400]); continue
    body = e.get("content") or e.get("text") or e.get("result") or e.get("arguments") or e.get("input") or ""
    if not isinstance(body, str):
        body = json.dumps(body)
    print(f"[{t}] {name} {body[:200]}".strip())
'

    echo "[hermes-loop] $(date -u +%FT%TZ) run finished (exit ${PIPESTATUS[0]})"
  fi
  # backlog: go again after a short pause; otherwise wait the normal interval
  if [ "${n:-0}" -ge 2 ]; then sleep 60; else sleep $(( ${REVIEW_EVERY_MIN:-20} * 60 )); fi
done
