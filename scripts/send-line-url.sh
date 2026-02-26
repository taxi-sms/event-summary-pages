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
TO_USER="${LINE_TO_USER_ID:-}"
TO_GROUP="${LINE_TO_GROUP_ID:-}"
TO_GROUPS_RAW="${LINE_TO_GROUP_IDS:-}"
USE_BROADCAST="${LINE_BROADCAST:-0}"
URL="${1:-https://taxi-sms.github.io/event-summary-pages/?v=$(date +%Y%m%d-%H%M%S)}"
LABEL="${2:-イベントまとめを更新しました}"
TEXT="${LABEL}\n${URL}"

if [[ -z "$TOKEN" ]]; then
  echo "LINE送信失敗: LINE_CHANNEL_ACCESS_TOKEN が未設定です。"
  exit 1
fi

# Priority: broadcast > groups(list) > group(single) > user
send_push() {
  local target_type="$1"
  local target_id="$2"
  local endpoint="https://api.line.me/v2/bot/message/push"
  local payload
  local tmp_body http_code
  payload=$(printf '{"to":"%s","messages":[{"type":"text","text":"%s"}]}' "$target_id" "$TEXT")
  tmp_body="$(mktemp)"
  http_code=$(curl -sS -o "$tmp_body" -w '%{http_code}' \
    -X POST "$endpoint" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $TOKEN" \
    --data "$payload")
  if [[ "$http_code" =~ ^2 ]]; then
    echo "LINE送信成功 (${target_type}): $URL -> ${target_id}"
    rm -f "$tmp_body"
    return 0
  fi
  echo "LINE送信失敗 (HTTP $http_code, target=${target_type}, id=${target_id})"
  cat "$tmp_body"
  rm -f "$tmp_body"
  return 1
}

if [[ "$USE_BROADCAST" == "1" ]]; then
  TMP_BODY="$(mktemp)"
  HTTP_CODE=$(curl -sS -o "$TMP_BODY" -w '%{http_code}' \
    -X POST "https://api.line.me/v2/bot/message/broadcast" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $TOKEN" \
    --data "$(printf '{"messages":[{"type":"text","text":"%s"}]}' "$TEXT")")
  if [[ "$HTTP_CODE" =~ ^2 ]]; then
    echo "LINE送信成功 (broadcast): $URL"
    rm -f "$TMP_BODY"
    exit 0
  fi
  echo "LINE送信失敗 (HTTP $HTTP_CODE, target=broadcast)"
  cat "$TMP_BODY"
  rm -f "$TMP_BODY"
  exit 1
elif [[ -n "$TO_GROUPS_RAW" ]]; then
  # Accept comma/newline/full-width comma/semicolon separated values from env/Secrets.
  TO_GROUPS_RAW="$(printf '%s' "$TO_GROUPS_RAW" | tr '，；;' ',,,')"
  TO_GROUPS_RAW="${TO_GROUPS_RAW//$'\r'/}"
  TO_GROUPS_RAW="${TO_GROUPS_RAW//$'\n'/,}"
  IFS=',' read -r -a GROUPS <<< "$TO_GROUPS_RAW"
  SENT=0
  FAIL=0
  VALID=0
  for gid in "${GROUPS[@]}"; do
    gid="$(printf '%s' "$gid" | tr -d '[:space:]\"')"
    [[ -z "$gid" ]] && continue
    VALID=$((VALID + 1))
    if send_push "group" "$gid"; then
      SENT=$((SENT + 1))
    else
      FAIL=$((FAIL + 1))
    fi
  done
  if (( VALID == 0 )); then
    echo "LINE送信失敗: LINE_TO_GROUP_IDS に有効なIDがありません。"
    exit 1
  fi
  if (( FAIL > 0 )); then
    echo "LINE複数グループ送信: 一部失敗（成功=${SENT}, 失敗=${FAIL}）"
    exit 1
  fi
  echo "LINE複数グループ送信成功: ${SENT}件"
  exit 0
elif [[ -n "$TO_GROUP" ]]; then
  send_push "group" "$TO_GROUP"
  exit $?
elif [[ -n "$TO_USER" ]]; then
  send_push "user" "$TO_USER"
  exit $?
else
  echo "LINE送信失敗: 宛先未設定です。LINE_TO_GROUP_IDS / LINE_TO_GROUP_ID / LINE_TO_USER_ID を設定するか LINE_BROADCAST=1 を使用してください。"
  exit 1
fi
