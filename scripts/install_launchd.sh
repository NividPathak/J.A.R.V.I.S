#!/usr/bin/env bash
# Install the two launchd agents that make JARVIS a daily habit rather than a
# thing you remember to run:
#
#   poller    keeps the cache fresh, restarts if it dies, survives reboot
#   briefing  fires each morning
#
#   ./scripts/install_launchd.sh              # briefing at 07:00, notification only
#   ./scripts/install_launchd.sh --speak      # ...and read aloud
#   ./scripts/install_launchd.sh --hour 6     # different time
#   ./scripts/install_launchd.sh --dry-run    # write to /tmp and lint, install nothing
#   ./scripts/install_launchd.sh --uninstall  # remove both
#
# launchd is used rather than cron because it survives reboots, restarts a dead
# poller on its own, and doesn't need a login shell.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
AGENTS="$HOME/Library/LaunchAgents"
POLLER_LABEL="com.nivid.jarvis.poller"
BRIEFING_LABEL="com.nivid.jarvis.briefing"

HOUR=7
MINUTE=0
SPEAK=""
UNINSTALL=""
DRY_RUN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --speak)     SPEAK="<string>--speak</string>"; shift ;;
    --hour)      HOUR="$2"; shift 2 ;;
    --minute)    MINUTE="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --dry-run)   DRY_RUN=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

# Write somewhere harmless so the output can be inspected and linted without
# registering anything with launchd.
if [[ -n "$DRY_RUN" ]]; then
  AGENTS="$(mktemp -d)"
fi

unload() {
  local label="$1"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  rm -f "$AGENTS/$label.plist"
}

if [[ -n "$UNINSTALL" ]]; then
  unload "$POLLER_LABEL"
  unload "$BRIEFING_LABEL"
  echo "Removed both agents."
  exit 0
fi

[[ -x "$PYTHON" ]] || { echo "No venv at $PYTHON — run: python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt" >&2; exit 1; }
mkdir -p "$AGENTS" "$ROOT/var"

cat > "$AGENTS/$POLLER_LABEL.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$POLLER_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$ROOT/poll.py</string>
    <string>run</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$ROOT/var/poller.log</string>
  <key>StandardErrorPath</key><string>$ROOT/var/poller.log</string>
</dict>
</plist>
PLIST

cat > "$AGENTS/$BRIEFING_LABEL.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$BRIEFING_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$ROOT/brief.py</string>
    <string>--notify</string>
    <string>--quiet</string>
    $SPEAK
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>$MINUTE</integer>
  </dict>
  <key>StandardOutPath</key><string>$ROOT/var/briefing.log</string>
  <key>StandardErrorPath</key><string>$ROOT/var/briefing.log</string>
</dict>
</plist>
PLIST

for label in "$POLLER_LABEL" "$BRIEFING_LABEL"; do
  plutil -lint "$AGENTS/$label.plist"
  if [[ -n "$DRY_RUN" ]]; then
    continue
  fi
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$label.plist"
  echo "loaded $label"
done

if [[ -n "$DRY_RUN" ]]; then
  echo
  echo "Dry run — nothing installed. Generated in $AGENTS:"
  sed -n 's/^.*<string>\(.*\)<\/string>.*$/    \1/p' "$AGENTS/$BRIEFING_LABEL.plist" | head -6
  exit 0
fi

printf '\nBriefing runs at %02d:%02d%s.\n' "$HOUR" "$MINUTE" "${SPEAK:+ (spoken)}"
echo "Logs: $ROOT/var/{poller,briefing}.log"
echo "Test it now:  $PYTHON $ROOT/brief.py --notify"
echo "Remove:       ./scripts/install_launchd.sh --uninstall"
