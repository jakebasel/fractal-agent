#!/bin/sh
# usage: propose.sh '{"title": "...", "rule": "IF ... THEN ...", "rule_ref": "§x", "note": "..."}'  (or a file path)
. /opt/data/trading-review/.token
body="$1"
[ -f "$body" ] && body=$(cat "$body")
printf '%s' "$body" | python3 -c 'import sys,json; json.loads(sys.stdin.read())' 2>&1 | head -2 | grep -q . && { echo "INVALID JSON"; exit 2; }
printf '%s' "$body" | curl -sS -m 30 -w '\nHTTP %{http_code}\n' -X POST "${AGENT_URL:-https://agent.motivationpro.tech}/api/hypotheses/propose" \
  -H "Content-Type: application/json" -H "X-Agent-Token: ${AGENT_TOKEN}" --data-binary @-
