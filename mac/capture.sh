#!/bin/bash
# Sends one screenshot of the TradingView screen to the fractal agent.
# launchd runs this every 30 seconds (see install.sh). Settings: ~/.fractal-agent.env
#   AGENT_URL=https://agent.motivationpro.tech
#   AGENT_TOKEN=...            (same value as AGENT_TOKEN on the server)
#   SCREEN=1                   (display number: 1 = main display; 2 = external, ...)
#   ACTIVE_HOURS="0-23"        (optional ET hour range to send, e.g. "1-12")
set -u
ENV_FILE="$HOME/.fractal-agent.env"
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE"; exit 1; }
# shellcheck disable=SC1090
source "$ENV_FILE"
: "${AGENT_URL:?}" "${AGENT_TOKEN:?}"
SCREEN="${SCREEN:-1}"
ACTIVE_HOURS="${ACTIVE_HOURS:-0-23}"

# skip outside the chosen hours (ET) and on Saturdays
HOUR=$(TZ=America/New_York date +%-H)
DOW=$(TZ=America/New_York date +%u)   # 6 = Saturday
LO=${ACTIVE_HOURS%-*}; HI=${ACTIVE_HOURS#*-}
[ "$DOW" = "6" ] && exit 0
{ [ "$HOUR" -lt "$LO" ] || [ "$HOUR" -gt "$HI" ]; } && exit 0

# skip when the screen is locked or asleep (nothing useful to send)
if /usr/bin/python3 -c 'import Quartz,sys; d=Quartz.CGSessionCopyCurrentDictionary(); sys.exit(0 if d and d.get("CGSSessionScreenIsLocked",0) else 1)' 2>/dev/null; then
  exit 0
fi

TMP=$(mktemp -t fa).jpg
trap 'rm -f "$TMP"' EXIT
/usr/sbin/screencapture -x -t jpg -D "$SCREEN" "$TMP" || exit 1
# shrink to ~2000px wide, quality 70: ~300-500 KB, still readable for the vision model
/usr/bin/sips -Z 2000 -s formatOptions 70 "$TMP" >/dev/null 2>&1

/usr/bin/curl -sS -m 20 -X POST --data-binary @"$TMP" \
  -H "Content-Type: image/jpeg" -H "X-Agent-Token: $AGENT_TOKEN" \
  "$AGENT_URL/screenshot" >/dev/null
