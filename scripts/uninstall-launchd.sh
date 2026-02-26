#!/usr/bin/env bash
set -euo pipefail

LABEL="com.taxi-sms.event-summary-pages"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

echo "launchd 設定を削除しました: $PLIST_PATH"
