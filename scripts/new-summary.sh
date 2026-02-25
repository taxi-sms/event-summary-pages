#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

DATE_STR="${1:-$(date +%F)}"
FORCE="${2:-}"

TEMPLATE="event-summary.template.html"
TARGET="event-summary.html"
ARCHIVE_DIR="archive"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "${TEMPLATE} が見つかりません。"
  exit 1
fi

if [[ -f "$TARGET" && "$FORCE" != "--force" ]]; then
  mkdir -p "$ARCHIVE_DIR"
  stamp="$(date +%Y%m%d-%H%M%S)"
  cp "$TARGET" "$ARCHIVE_DIR/event-summary-${stamp}.html"
  echo "既存 ${TARGET} を ${ARCHIVE_DIR}/event-summary-${stamp}.html にバックアップしました。"
fi

cp "$TEMPLATE" "$TARGET"
# Template placeholder replacement (first occurrence only is enough in current template)
sed -i '' "s/YYYY-MM-DD/${DATE_STR}/g" "$TARGET"

echo "${TARGET} をテンプレートから作成しました。日付: ${DATE_STR}"
echo "次: 内容を編集後、./scripts/publish-pages.sh \"${DATE_STR} update\""
