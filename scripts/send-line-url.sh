#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env.line" ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env.line
  set +a
fi

LINE_AUTO_SEND="${LINE_AUTO_SEND:-0}"
if [[ "$LINE_AUTO_SEND" != "1" ]]; then
  echo "LINE送信スキップ（.env.line で LINE_AUTO_SEND=1 にすると有効化）"
  exit 0
fi

TOKEN="${LINE_CHANNEL_ACCESS_TOKEN:-}"
TO="${LINE_TO_USER_ID:-}"
USE_BROADCAST="${LINE_BROADCAST:-0}"
URL="${1:-https://taxi-sms.github.io/event-summary-pages/?v=$(date +%Y%m%d-%H%M%S)}"
LABEL="${2:-イベントまとめを更新しました}"
TEXT="${LABEL}\n${URL}"

if [[ -z "$TOKEN" ]]; then
  echo "LINE送信失敗: LINE_CHANNEL_ACCESS_TOKEN が未設定です。"
  exit 1
fi

if [[ "$USE_BROADCAST" != "1" && -z "$TO" ]]; then
  echo "LINE送信失敗: LINE_TO_USER_ID が未設定です（または LINE_BROADCAST=1 を使用）。"
  exit 1
fi

if [[ "$USE_BROADCAST" == "1" ]]; then
  ENDPOINT="https://api.line.me/v2/bot/message/broadcast"
  PAYLOAD=$(printf '{"messages":[{"type":"text","text":"%s"}]}' "$TEXT")
else
  ENDPOINT="https://api.line.me/v2/bot/message/push"
  PAYLOAD=$(printf '{"to":"%s","messages":[{"type":"text","text":"%s"}]}' "$TO" "$TEXT")
fi

TMP_BODY="$(mktemp)"
HTTP_CODE=$(curl -sS -o "$TMP_BODY" -w '%{http_code}' \
  -X POST "$ENDPOINT" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  --data "$PAYLOAD")

if [[ "$HTTP_CODE" =~ ^2 ]]; then
  echo "LINE送信成功: $URL"
  rm -f "$TMP_BODY"
  exit 0
fi

echo "LINE送信失敗 (HTTP $HTTP_CODE)"
cat "$TMP_BODY"
rm -f "$TMP_BODY"
exit 1
