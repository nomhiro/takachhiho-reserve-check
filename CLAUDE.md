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

### 着手前に必ず確認すること

予約ページが SSR か CSR か、5/8 のデータがどこから来るかは **未確認**。
Claude Code は以下をまず実施すること:

1. `curl` または `requests` で URL を取得し、HTML に「2026-05-08」「5/8」「5月8日」などが含まれるか確認
2. 含まれない場合は CSR の可能性が高い → ユーザーに Chrome DevTools の Network タブで内部APIを特定するよう依頼
3. 内部APIが見つかれば JSON 経由でアクセスする方針に変更

**未確認のままパース実装を始めない。** ユーザーに確認を取ること。

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
2. ユーザーに「サイトの実装形式（SSR/CSR、API有無）」を確認
3. fetcher / parser を fixture ベースのテスト先行で実装
4. state machine を実装（テスト4パターン全通り）
5. notifier をテストトピックで動作確認
6. workflow yaml を書く
7. ローカルで `python scripts/check.py --dry-run` 成功
8. テストトピックで E2E 確認 → 本番トピックに切り替え
