#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

HOUR="${1:-21}"
MINUTE="${2:-0}"
RUN_NOW="${3:-}"

if ! [[ "$HOUR" =~ ^[0-9]+$ ]] || ! [[ "$MINUTE" =~ ^[0-9]+$ ]]; then
  echo "使い方: ./scripts/install-launchd.sh [hour] [minute] [--run-now]"
  exit 1
fi
if (( HOUR < 0 || HOUR > 23 || MINUTE < 0 || MINUTE > 59 )); then
  echo "時刻が不正です。hour=0-23, minute=0-59"
  exit 1
fi

LABEL="com.taxi-sms.event-summary-pages"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/${LABEL}.plist"
STDOUT_LOG="$ROOT_DIR/logs/launchd.out.log"
STDERR_LOG="$ROOT_DIR/logs/launchd.err.log"
SCRIPT_PATH="$ROOT_DIR/scripts/auto-publish.sh"

mkdir -p "$LAUNCH_AGENTS_DIR" "$ROOT_DIR/logs"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>${SCRIPT_PATH}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${ROOT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key>
      <integer>${HOUR}</integer>
      <key>Minute</key>
      <integer>${MINUTE}</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${STDOUT_LOG}</string>
    <key>StandardErrorPath</key>
    <string>${STDERR_LOG}</string>

    <key>RunAtLoad</key>
    <false/>
  </dict>
</plist>
PLIST

# Reload job if it exists
launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

if [[ "$RUN_NOW" == "--run-now" ]]; then
  launchctl kickstart -k "gui/$(id -u)/${LABEL}"
fi

echo "launchd 設定をインストールしました: $PLIST_PATH"
echo "実行時刻: $(printf '%02d:%02d' "$HOUR" "$MINUTE") 毎日"
echo "確認コマンド: launchctl print gui/$(id -u)/${LABEL}"
echo "手動実行: launchctl kickstart -k gui/$(id -u)/${LABEL}"
