#!/bin/sh
# usage: propose.sh '{"title": "...", "rule": "IF ... THEN ...", "rule_ref": "§x", "note": "..."}'
. /opt/data/trading-review/.token
curl -sS -m 30 -o /dev/stderr -w '%{http_code}\n' -X POST "${AGENT_URL:-https://agent.motivationpro.tech}/api/hypotheses/propose" \
  -H "Content-Type: application/json" -H "X-Agent-Token: ${AGENT_TOKEN}" --data "$1"
