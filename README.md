# event-summary-pages

GitHub Pages で公開するイベントまとめページ用リポジトリです。

公開URL:
- https://taxi-sms.github.io/event-summary-pages/

## ファイル構成
- `event-summary.html`: 編集する本体（毎日更新）
- `index.html`: 公開用（`publish` 時に自動生成）
- `event-summary.template.html`: 新規作成用テンプレート
- `scripts/new-summary.sh`: テンプレートから当日ページを作成（旧版バックアップあり）
- `scripts/publish-pages.sh`: `index.html` 生成 + commit + push + キャッシュ回避URL表示 + （任意）LINE送信
- `scripts/send-line-url.sh`: LINE Messaging API でURL送信（`publish` から自動呼び出し可）
- `.env.line.example`: LINE連携の設定サンプル（実体は `.env.line`）
- `archive/`: `new-summary.sh` 実行時のバックアップ保存先

## 毎日の運用（最短）
1. 前日の内容を差分修正して `event-summary.html` を更新する
2. 画像がある場合はこのリポジトリ内に保存する（例: `*.jpg`）
3. 公開する（公開後、キャッシュ回避URLを表示）

```bash
./scripts/publish-pages.sh "2026-02-26 update"
```

## テンプレートから新しく始める（必要な日だけ）
```bash
./scripts/new-summary.sh 2026-02-27
```

- 既存の `event-summary.html` は自動で `archive/` にバックアップされます
- その後、`event-summary.html` を編集してください

## LINE自動送信（任意）
### 1. 設定ファイル作成
```bash
cp .env.line.example .env.line
```

### 2. `.env.line` を編集
- `LINE_AUTO_SEND=1`
- `LINE_CHANNEL_ACCESS_TOKEN=...`
- `LINE_TO_USER_ID=U...`（特定相手に送る場合）
- または `LINE_BROADCAST=1`（公式アカウント友だち全体に送る場合）

### 3. 公開時に自動送信
```bash
./scripts/publish-pages.sh "2026-02-26 update"
```

- push 成功後に `?v=YYYYMMDD-HHMMSS` 付きURLを LINE へ送信します
- `.env.line` が無い / `LINE_AUTO_SEND=0` の場合は自動送信をスキップします

## 編集ルール（運用統一）
- 時刻は `HH:MM` 形式（例: `16:15`）
- フライヤーがない場合は「フライヤーなし（掲載なし）」と明記
- PDFしかない場合はPDFリンクを残す
- 公開時は `event-summary.html` を直接編集し、`index.html` は手で触らない

## 初回セットアップ（完了済み）
- GitHub repo 作成
- GitHub Pages 有効化（`main` / root）
- `gh auth login`
