#!/bin/sh
# usage: get_shot.sh <screenshot name>  -> downloads it to /opt/data/trading-review/shots/<name>
. /opt/data/trading-review/.token
mkdir -p /opt/data/trading-review/shots
out="/opt/data/trading-review/shots/$(basename "$1")"
curl -sS -m 30 -o "$out" -w '%{http_code}\n' "${AGENT_URL:-https://agent.motivationpro.tech}/shot/$(basename "$1")?token=${AGENT_TOKEN}" && echo "$out"
