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
- `scripts/auto-publish.sh`: `launchd` から呼ぶ自動実行ラッパー
- `scripts/prepublish-hook.sh.example`: 事前抽出・更新処理の差し込み用テンプレート
- `scripts/install-launchd.sh`: 毎日定時実行の `launchd` 登録
- `scripts/uninstall-launchd.sh`: `launchd` 登録解除
- `.env.line.example`: LINE連携の設定サンプル（実体は `.env.line`）
- `launchd/com.taxi-sms.event-summary-pages.plist.example`: `launchd` 設定サンプル
- `archive/`: `new-summary.sh` 実行時のバックアップ保存先
- `logs/`: 自動実行ログ（git管理しない）

## 毎日の運用（手動）
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

※送信先は `groupId` / `userId` / `broadcast` に対応（優先順位: `broadcast > group > user`）
### 1. 設定ファイル作成
```bash
cp .env.line.example .env.line
```

### 2. `.env.line` を編集
- `LINE_AUTO_SEND=1`
- `LINE_CHANNEL_ACCESS_TOKEN=...`
- `LINE_TO_GROUP_ID=C...`（グループに送る場合。おすすめ）
- `LINE_TO_USER_ID=U...`（特定相手に送る場合）
- または `LINE_BROADCAST=1`（公式アカウント友だち全体に送る場合）

### 3. 動作テスト
```bash
./scripts/send-line-url.sh "https://taxi-sms.github.io/event-summary-pages/?v=test"
```

## 完全自動（Mac / launchd）
### できること
- 毎日指定時刻に `scripts/auto-publish.sh` を実行
- `publish-pages.sh` が `push` + キャッシュ回避URL表示
- `.env.line` 設定済みなら LINE に URL を自動送信

### 注意（重要）
- **現時点では HTML の中身そのものは自動更新されません**（今のままでは前回内容を再公開するだけ）
- 将来スクレイピングまで自動化したい場合は `scripts/prepublish-hook.sh` を作成して、`event-summary.html` を更新する処理を入れます

### 登録（例: 毎日 21:00）
```bash
./scripts/install-launchd.sh 21 0
```

### 登録 + 今すぐ1回実行
```bash
./scripts/install-launchd.sh 21 0 --run-now
```

### 状態確認
```bash
launchctl print gui/$(id -u)/com.taxi-sms.event-summary-pages
```

### 手動実行（launchd経由）
```bash
launchctl kickstart -k gui/$(id -u)/com.taxi-sms.event-summary-pages
```

### 解除
```bash
./scripts/uninstall-launchd.sh
```

## 編集ルール（運用統一）
- 時刻は `HH:MM` 形式（例: `16:15`）
- フライヤーがない場合は「フライヤーなし（掲載なし）」と明記
- PDFしかない場合はPDFリンクを残す
- 公開時は `event-summary.html` を直接編集し、`index.html` は手で触らない

## 初回セットアップ（完了済み）
- GitHub repo 作成
- GitHub Pages 有効化（`main` / root）
- `gh auth login`
