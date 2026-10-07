#!/bin/bash
# Installs the screenshot uploader as a launchd agent (runs every 30s while you're logged in).
#   bash mac/install.sh            install / reinstall
#   bash mac/install.sh uninstall  remove
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.jake.fractal-capture"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "${1:-}" = "uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"; echo "removed"; exit 0
fi

if [ ! -f "$HOME/.fractal-agent.env" ]; then
  cat > "$HOME/.fractal-agent.env" <<'EOF'
AGENT_URL=https://agent.motivationpro.tech
AGENT_TOKEN=PASTE_THE_SAME_TOKEN_AS_ON_THE_SERVER
SCREEN=1
ACTIVE_HOURS=0-23
EOF
  chmod 600 "$HOME/.fractal-agent.env"
  echo "Created ~/.fractal-agent.env — put the token in it, then run this again."
  exit 0
fi

chmod +x "$HERE/capture.sh"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$HERE/capture.sh</string></array>
  <key>StartInterval</key><integer>30</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/fractal-capture.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/fractal-capture.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed. First run will ask for Screen Recording permission (System Settings >"
echo "Privacy & Security > Screen Recording: allow 'bash'). Log: ~/Library/Logs/fractal-capture.log"
