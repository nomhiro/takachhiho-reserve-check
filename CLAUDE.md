# CLAUDE.md

このファイルは Claude Code がこのリポジトリで作業する際の前提情報をまとめたものです。
**作業を始める前に必ず `docs/` 配下の3ドキュメントを読んでから実装してください。**

## プロジェクト概要

高千穂峡貸しボート予約サイトの 2026/5/8 の空き状況を1時間に1回チェックし、
**状態変化時のみ** ntfy 経由でスマホ通知する GitHub Actions ジョブ。

- 対象URL: `https://eipro.jp/takachiho1/eventCalendars/index`
- 対象日: `2026-05-08`
- 通知先: ntfy.sh（無料・トピックベース）
- 実行環境: GitHub Actions（無料枠内）

## ディレクトリ構成

```
.
├── .github/workflows/
│   └── watch.yml              # cron + dry-run + weekly health check
├── scripts/
│   ├── check.py               # メインエントリ
│   ├── fetcher.py             # サイトからのデータ取得
│   ├── parser.py              # 5/8 の空き状況を抽出
│   ├── notifier.py            # ntfy 通知
│   └── state.py               # state.json の読み書き
├── state/
│   └── state.json             # 最後の状態（gitで永続化）
├── tests/
│   ├── fixtures/              # 固定HTML/JSONサンプル
│   ├── test_parser.py
│   ├── test_state_machine.py
│   └── test_notifier.py
├── docs/
│   ├── requirements.md
│   ├── specification.md
│   └── harness-engineering.md
├── requirements.txt
├── CLAUDE.md
└── README.md
```

## 実装上の重要事項

### サイト実装形式（調査済み・確定）

予約ページは **CSR**。HTML に 5/8 の文字列は出現せず、jQuery 版 FullCalendar が以下の内部 API を叩いて描画している:

- **エンドポイント:** `POST https://eipro.jp/takachiho1/eventCalendars/search`
- **認証:** 不要（Cookie / CSRF トークン無しで JSON が返る）
- **リクエスト（form-urlencoded）:**
  - `data[conds][ServiceView][max_session_dateOver]` … 期間開始 (`YYYY-MM-DD`)
  - `data[conds][ServiceView][min_session_dateUnder]` … 期間終了 (`YYYY-MM-DD`)
  - `calendar_view_name=month`、`calendar_type=month`
- **レスポンス:** `{"results": [...], "errors": [], ...}`。各エントリは `service_date` (`YYYY/MM/DD`)、`ordable` (bool)、`color`、`title`(HTML) などを持つ
- **判定ロジック:** `service_date == "2026/05/08"` のエントリで `ordable: true` なら "available"、それ以外（`false` or エントリ無し）は "full"

サイト仕様変更時は `tests/fixtures/{available,full,error,missing_target}.json` を更新し parser を修正すること。

### コーディング規約

- Python 3.11+
- 標準ライブラリ + `requests` + `beautifulsoup4` のみ（軽量に保つ）
- 型ヒント必須
- ロガーで標準出力に構造化ログを出す（Actions のログから追えるように）
- `--dry-run` フラグで通知送信を抑止できること
- すべてのHTTPリクエストに識別可能な User-Agent を付ける（例: `takachiho-watch/0.1 (personal monitoring; contact via repo)`）

### テスト

- すべての PR でテスト必須
- 外部HTTPは必ずモック化
- `tests/fixtures/` に「空きあり」「満室」「エラー」3種のサンプルを用意

### コミット規約

- Conventional Commits 推奨（`feat:`, `fix:`, `chore(state):` など）
- state.json の自動コミットは `chore(state): update at YYYY-MM-DDTHH:MM` 形式

### セキュリティ

- ntfy トピック名は **絶対にコミットしない**。`NTFY_TOPIC` Secret から読む
- リポジトリは Private 推奨
- ログにトピック名を出力しないこと

## ユーザーについて

- 開発者: Hiroki（Polario / KTC）
- 環境: Windows 11 + WSL2 Ubuntu 24.04 + Docker Desktop
- 好み: TPS 的な「自働化」「見える化」観点。冗長な実装より、状態遷移が一目で分かるシンプルな設計を好む
- 仕事の性質上、production-ready な品質を求める（エラーハンドリング・観測性を妥協しない）

## 開発ループの推奨

1. `docs/` を読む
2. fixture を更新（仕様変更があれば）
3. fetcher / parser を fixture ベースのテスト先行で修正
4. state machine を変更する場合は遷移マトリクスのテストを追加
5. ローカルで `python -m scripts.check --dry-run` 成功
6. テストトピックで E2E 確認 → 本番トピックに切り替え

## 実装上の確定事項（参考）

- 起動コマンドは `python -m scripts.check`（モジュール実行）。`python scripts/check.py` でも動くようパスブートストラップを入れている
- ログは UTF-8 固定（`sys.stdout.reconfigure(encoding="utf-8")`）。Windows コンソールでは表示が化けるが、ファイル出力と Actions ログでは正常
- API 取得失敗は 5xx/タイムアウトで指数バックオフ 3 回（1s, 2s, 4s）、4xx は即 `FetchError`
- ntfy 送信失敗は無限ループ回避のためログ出力のみで握りつぶす（spec §8 準拠）
