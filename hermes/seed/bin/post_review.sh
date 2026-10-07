#!/bin/sh
# usage: post_review.sh '<json body>'   or   post_review.sh /path/to/body.json
# Validates the JSON first (prints the parse error if any), POSTs to /api/reviews, prints the
# server reply and the HTTP code. 200 = filed.
. /opt/data/trading-review/.token
body="$1"
[ -f "$body" ] && body=$(cat "$body")
printf '%s' "$body" | python3 -c 'import sys,json; json.loads(sys.stdin.read())' 2>&1 | head -2 | grep -q . && { echo "INVALID JSON: fix the body (watch quotes and newlines) and retry"; exit 2; }
printf '%s' "$body" | curl -sS -m 30 -w '\nHTTP %{http_code}\n' -X POST "${AGENT_URL:-https://agent.motivationpro.tech}/api/reviews" \
  -H "Content-Type: application/json" -H "X-Agent-Token: ${AGENT_TOKEN}" --data-binary @-
