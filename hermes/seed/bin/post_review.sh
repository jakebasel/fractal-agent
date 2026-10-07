#!/bin/sh
# usage: post_review.sh '<json body>'  -> POST /api/reviews on the paper agent
. /opt/data/trading-review/.token
curl -sS -m 30 -o /dev/stderr -w '%{http_code}\n' -X POST "${AGENT_URL:-https://agent.motivationpro.tech}/api/reviews" \
  -H "Content-Type: application/json" -H "X-Agent-Token: ${AGENT_TOKEN}" --data "$1"
