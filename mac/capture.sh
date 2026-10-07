#!/bin/bash
# Sends one screenshot of the TradingView screen to the fractal agent.
# launchd runs this every 30 seconds (see install.sh). Settings: ~/.fractal-agent.env
#   AGENT_URL=https://agent.motivationpro.tech
#   AGENT_TOKEN=...            (same value as AGENT_TOKEN on the server)
#   SCREEN=1                   (display number: 1 = main display; 2 = external, ...)
#   ACTIVE_HOURS="0-23"        (optional ET hour range to send, e.g. "1-12")
#   CAPTURE=windows            windows (default): only TradingView windows, even if covered
#                              screen: the whole display (old behaviour)
#   TV_MATCH="..."             regex for window titles that count as TradingView
# TradingView in Chrome: it must be the ACTIVE tab of its window to be capturable, so keep it in
# its own Chrome window (drag the tab out). Then it is captured even when covered.
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

HERE="$(cd "$(dirname "$0")" && pwd)"
STATE="$HOME/Library/Logs/fractal-capture.state"
note() {   # log only when the situation changes, not every 30 seconds
  [ "$(cat "$STATE" 2>/dev/null)" = "$1" ] && return
  echo "$1" > "$STATE"; echo "$(date '+%Y-%m-%d %H:%M:%S') $1"
}
send() {   # file, query string
  # shrink to ~2000px wide, quality 70: ~300-500 KB, still readable for the vision model
  /usr/bin/sips -Z 2000 -s formatOptions 70 "$1" >/dev/null 2>&1
  /usr/bin/curl -sS -m 20 -X POST --data-binary @"$1" \
    -H "Content-Type: image/jpeg" -H "X-Agent-Token: $AGENT_TOKEN" \
    "$AGENT_URL/screenshot$2" >/dev/null
}

TMPD=$(mktemp -d -t fa)
trap 'rm -rf "$TMPD"' EXIT

if [ "${CAPTURE:-windows}" = "screen" ]; then
  /usr/sbin/screencapture -x -t jpg -D "$SCREEN" "$TMPD/s.jpg" || { note "capture failed"; exit 1; }
  send "$TMPD/s.jpg" "?kind=screen" && note "ok: whole screen"
  exit 0
fi

# Where is TradingView? Ask Chrome for the window whose ACTIVE tab is tradingview.com (a tab in
# the background cannot be captured: Chrome does not draw it), then list capturable windows.
CHROME=$(/usr/bin/osascript 2>/dev/null <<'AS'
tell application "Google Chrome"
  if not running then return ""
  set tvBounds to ""
  set hiddenTabs to 0
  repeat with w in windows
    set u to URL of active tab of w
    if u contains "tradingview.com" then
      if tvBounds is "" then
        set b to bounds of w
        set tvBounds to ((item 1 of b) as text) & "," & ((item 2 of b) as text) & "," & ((item 3 of b) as text) & "," & ((item 4 of b) as text)
      end if
    else
      repeat with t in tabs of w
        if URL of t contains "tradingview.com" then set hiddenTabs to hiddenTabs + 1
      end repeat
    end if
  end repeat
  return tvBounds & ";" & hiddenTabs
end tell
AS
)
CHROME_BOUNDS=${CHROME%%;*}
CHROME_HIDDEN=${CHROME##*;}
IDS=$(/usr/bin/osascript -l JavaScript "$HERE/windows.js" "${TV_MATCH:-TradingView}" "$CHROME_BOUNDS" 2>/dev/null | cut -d'|' -f1)
status() {   # tell the server why nothing was sent, so the dashboard can show it
  /usr/bin/curl -sS -m 10 -X POST -H "X-Agent-Token: $AGENT_TOKEN" \
    "$AGENT_URL/capture_status?state=$1" >/dev/null 2>&1
}
if [ -z "$IDS" ]; then
  if [ "${CHROME_HIDDEN:-0}" != "0" ] && [ "${CHROME_HIDDEN:-0}" != "" ]; then
    note "TradingView tab is in the background: nothing sent (drag it into its own Chrome window)"
    status background_tab
  else
    note "no TradingView window open: nothing sent"
    status not_open
  fi
  exit 0
fi
BATCH=$(date +%s)
N=0
for ID in $IDS; do
  # -l captures that window's own pixels, even when other windows cover it; -o drops the shadow
  if /usr/sbin/screencapture -x -o -t jpg -l "$ID" "$TMPD/$N.jpg" 2>/dev/null && [ -s "$TMPD/$N.jpg" ]; then
    send "$TMPD/$N.jpg" "?batch=$BATCH&part=$N&kind=window"
    N=$((N + 1))
  fi
  [ "$N" -ge 4 ] && break
done
if [ "$N" -gt 0 ]; then note "ok: $N TradingView window(s)"; else note "TradingView found but capture failed (Screen Recording permission?)"; status capture_failed; fi
