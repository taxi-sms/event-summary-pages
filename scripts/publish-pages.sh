#!/usr/bin/env bash
set -euo pipefail

# Publish the current event summary to GitHub Pages.
# Usage:
#   ./scripts/publish-pages.sh "2026-02-26 update"
# If message is omitted, today's date is used.
# After push, it prints a cache-busting URL and optionally sends it to LINE.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export TZ="Asia/Tokyo"
export LC_ALL="${LC_ALL:-C}"

BASE_URL="https://taxi-sms.github.io/event-summary-pages/"
MSG="${1:-$(date +%F) update}"
PAGES_WAIT_TIMEOUT_SEC="${PAGES_WAIT_TIMEOUT_SEC:-180}"
PAGES_WAIT_INTERVAL_SEC="${PAGES_WAIT_INTERVAL_SEC:-5}"

wait_for_pages_reflection() {
  local url="$1"
  local marker="$2"
  local timeout="$3"
  local interval="$4"
  local started now elapsed page

  started="$(date +%s)"
  while :; do
    if page="$(curl -fsSL --max-time 15 "${url}&_probe=$(date +%s)" 2>/dev/null)" \
      && printf '%s' "$page" | grep -Fq "$marker"; then
      echo "Pages反映確認: OK"
      return 0
    fi

    now="$(date +%s)"
    elapsed=$((now - started))
    if (( elapsed >= timeout )); then
      echo "Pages反映確認: タイムアウト（${timeout}s）"
      return 1
    fi
    sleep "$interval"
  done
}

if [[ ! -f "event-summary.html" ]]; then
  echo "event-summary.html が見つかりません。"
  echo "テンプレートから作る場合: ./scripts/new-summary.sh"
  exit 1
fi

cp event-summary.html index.html

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "Gitリポジトリではありません。"
  exit 1
}

# Dedicated Pages repo想定のため、日々の変更をまとめて stage
# (HTML, 画像, scripts, README, archive除外したい場合は手動運用に切替)
git add -A

if git diff --cached --quiet; then
  echo "差分がないため push しません。"
  VERSION_STAMP="$(date +%Y%m%d-%H%M%S)"
  echo "確認用URL(キャッシュ回避): ${BASE_URL}?v=${VERSION_STAMP}"
  exit 0
fi

VERSION_STAMP="$(date +%Y%m%d-%H%M%S)"
BUILD_MARKER="PAGES_BUILD_JST:${VERSION_STAMP}"
TMP_INDEX="$(mktemp)"
{
  printf '<!-- %s -->\n' "$BUILD_MARKER"
  cat index.html
} > "$TMP_INDEX"
mv "$TMP_INDEX" index.html
git add index.html

git commit -m "pages: ${MSG}"
git push

CACHE_BUST_URL="${BASE_URL}?v=${VERSION_STAMP}"

echo "Push完了。公開URL: ${BASE_URL}"
echo "確認/共有URL(キャッシュ回避): ${CACHE_BUST_URL}"

PAGES_READY=0
if wait_for_pages_reflection "$CACHE_BUST_URL" "$BUILD_MARKER" "$PAGES_WAIT_TIMEOUT_SEC" "$PAGES_WAIT_INTERVAL_SEC"; then
  PAGES_READY=1
else
  echo "警告: GitHub Pages 側の配信反映を確認できませんでした（ブラウザ/LINE側で古い内容が見える可能性あり）。"
fi

if [[ -x "./scripts/send-line-url.sh" ]]; then
  if ! ./scripts/send-line-url.sh "$CACHE_BUST_URL" "イベントまとめを更新しました"; then
    echo "LINE送信は失敗しました（公開は完了しています）。"
  elif [[ "$PAGES_READY" -ne 1 ]]; then
    echo "LINE送信は実施しましたが、Pages反映確認は未完了です。"
  fi
fi
