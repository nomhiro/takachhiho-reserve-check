# 仕様書 — takachiho-watch

## 1. アーキテクチャ概要

```
┌─────────────────────────────────────────────────┐
│ GitHub Actions (cron: 5 * * * *)                │
│                                                 │
│  ┌──────────┐   ┌─────────┐   ┌────────────┐    │
│  │ fetcher  │──▶│ parser  │──▶│state machine│   │
│  └──────────┘   └─────────┘   └─────┬──────┘    │
│   GET site      extract 5/8     compare with    │
│                  status         state.json      │
│                                       │         │
│                                       ▼         │
│                                 ┌──────────┐    │
│                                 │ notifier │    │
│                                 └────┬─────┘    │
│                                      │          │
│                                      ▼          │
│                              update state.json  │
│                              + git commit       │
└─────────────────────────────────────────────────┘
                                       │
                                       ▼ HTTPS POST
                                ┌─────────────┐
                                │  ntfy.sh    │
                                └──────┬──────┘
                                       │ Push
                                       ▼
                                ┌─────────────┐
                                │スマホ通知    │
                                └─────────────┘
```

## 2. 技術スタック

| 領域 | 採用 | 理由 |
|---|---|---|
| 実行環境 | GitHub Actions (ubuntu-latest) | 無料・cronネイティブ・state.jsonをgit管理できる |
| 言語 | Python 3.11+ | 標準ライブラリと requests で完結 |
| HTTP | requests | デファクト |
| HTMLパース | BeautifulSoup4 | サイトがSSRの場合に使用。CSRなら不要 |
| 通知 | ntfy.sh | 認証不要・無料・iOS/Android両対応・priority/tag対応 |
| 状態保存 | JSON file in repo | 別途DB不要・Git履歴で変化が見える |
| テスト | pytest | デファクト |

## 3. 事前調査タスク（実装前に必須）

予約ページの実装形式が未確認のため、Claude Code は実装前に以下を行う:

### 3.1 SSR/CSR 判定

```bash
curl -A "Mozilla/5.0 (compatible; takachiho-watch/0.1)" \
  https://eipro.jp/takachiho1/eventCalendars/index | \
  grep -E "2026-05-08|2026/05/08|5月8日|0508"
```

- ヒットあり → SSR。HTMLパースで進める
- ヒットなし → CSR の可能性大。次へ

### 3.2 内部API特定（CSRの場合）

ユーザーに以下を依頼する:

1. Chrome で対象ページを開く
2. DevTools (F12) → Network タブ → `Fetch/XHR` フィルタ
3. ページをリロード、または5月のカレンダーへ遷移
4. 空き状況を返している JSON エンドポイントを特定
5. リクエストURL、メソッド、ヘッダ、レスポンス例を共有

### 3.3 セッション/CSRF確認

- セッションクッキーが必要か
- CSRFトークンが必要か
- 必要な場合は2段階リクエスト（HTML取得 → トークン抽出 → API呼び出し）に変更

## 4. ファイル構成

```
.
├── .github/workflows/
│   └── watch.yml
├── scripts/
│   ├── check.py              # エントリポイント
│   ├── fetcher.py            # サイト取得
│   ├── parser.py             # 5/8抽出
│   ├── notifier.py           # ntfy送信
│   └── state.py              # 状態管理
├── state/
│   └── state.json
├── tests/
│   ├── fixtures/
│   │   ├── available.html    # 空きありサンプル
│   │   ├── full.html         # 満室サンプル
│   │   └── error.html        # 異常レスポンス
│   ├── test_parser.py
│   ├── test_state_machine.py
│   └── test_notifier.py
├── requirements.txt
└── README.md
```

## 5. 状態遷移仕様

### 5.1 状態の定義

| 状態 | 意味 |
|---|---|
| `unknown` | 初期状態。または連続パース失敗中 |
| `full` | 5/8 に空き枠なし |
| `available` | 5/8 に空き枠あり |
| `error` | 連続失敗。アラート通知済み |

### 5.2 遷移マトリクス

| from \ to | full | available | error | unknown |
|---|---|---|---|---|
| `unknown` | サイレント | **🚨 urgent通知** | error通知 | – |
| `full` | サイレント | **🚨 urgent通知** | error通知 | – |
| `available` | 通常通知 | サイレント | error通知 | – |
| `error` | 復旧通知（low） | **🚨 urgent通知** | サイレント（既通知） | – |

### 5.3 状態ファイル形式 (`state/state.json`)

```json
{
  "target_date": "2026-05-08",
  "last_status": "full",
  "last_check_at": "2026-04-28T07:05:12+09:00",
  "last_change_at": "2026-04-28T07:05:12+09:00",
  "consecutive_errors": 0,
  "last_health_check_at": "2026-04-26T09:00:00+09:00"
}
```

## 6. 通知仕様

ntfy POST エンドポイント: `https://ntfy.sh/{TOPIC}`

### 6.1 空き検知（urgent）

```http
POST https://ntfy.sh/{TOPIC}
Title: 🚨 高千穂峡 5/8 空き検知！
Priority: urgent
Tags: rotating_light,boat
Click: https://eipro.jp/takachiho1/eventCalendars/index
Actions: view, "予約サイトを開く", https://eipro.jp/takachiho1/eventCalendars/index, clear=true

Body:
  検知時刻: 2026-04-28 07:05 JST
  急いで予約してください。
```

### 6.2 満室復帰（default）

```http
POST https://ntfy.sh/{TOPIC}
Title: 高千穂峡 5/8 満室に戻りました
Priority: default
Tags: x

Body:
  先ほどの空きは埋まったようです。
  検知時刻: 2026-04-28 09:05 JST
```

### 6.3 ヘルスチェック（low、毎週日曜）

```http
POST https://ntfy.sh/{TOPIC}
Title: takachiho-watch 稼働中
Priority: low
Tags: white_check_mark

Body:
  今週も監視継続中です。
  最終チェック: 2026-04-28 08:05 JST
  現在の状態: full
```

### 6.4 監視エラー（high、3回連続失敗時）

```http
POST https://ntfy.sh/{TOPIC}
Title: ⚠️ takachiho-watch エラー
Priority: high
Tags: warning

Body:
  3回連続で取得/パースに失敗しました。
  Actions ログを確認してください。
  https://github.com/{owner}/{repo}/actions
```

## 7. ワークフロー仕様 (`.github/workflows/watch.yml`)

```yaml
name: watch

on:
  schedule:
    # 毎時5分に実行（毎時0分はGitHub Actionsが混雑するため）
    - cron: '5 * * * *'
  workflow_dispatch:   # 手動実行可

# 同時実行を防ぐ
concurrency:
  group: watch
  cancel-in-progress: false

permissions:
  contents: write    # state.json コミットに必要

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 5

    steps:
      - uses: actions/checkout@v4

      - name: 5/8 を過ぎたら停止
        run: |
          if [ "$(date -u +%Y%m%d)" -gt "20260508" ]; then
            echo "監視期間終了"
            exit 0
          fi

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - run: pip install -r requirements.txt

      - name: Run check
        env:
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
        run: python scripts/check.py

      - name: Commit state
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add state/state.json
          git diff --cached --quiet || git commit -m "chore(state): update at $(date -u +%Y-%m-%dT%H:%MZ)"
          git push
```

別ジョブとしてヘルスチェック:

```yaml
  health:
    runs-on: ubuntu-latest
    if: github.event.schedule == '0 0 * * 0'   # UTC日曜0時 = JST日曜9時
    # ... NTFY_TOPIC に「稼働中」を送る
```

（実装上は同一ジョブ内で曜日判定のほうがシンプルでも可）

## 8. エラーハンドリング

| ケース | 対応 |
|---|---|
| HTTP 5xx / タイムアウト | 指数バックオフで最大3回リトライ（1s, 2s, 4s） |
| HTTP 4xx | リトライしない（仕様変更の可能性 → consecutive_errors++） |
| パース失敗 | consecutive_errors++、3回連続でアラート通知 |
| ntfy送信失敗 | Actionsログにのみ記録、無限ループ回避のため再通知しない |
| state.json 破損 | unknown 状態で再初期化、初回扱いで判定 |

## 9. ログ仕様

構造化ログ（JSON Lines）で標準出力へ:

```json
{"ts":"2026-04-28T07:05:12+09:00","level":"INFO","event":"check_start","target":"2026-05-08"}
{"ts":"2026-04-28T07:05:13+09:00","level":"INFO","event":"fetch_ok","status_code":200,"bytes":15234}
{"ts":"2026-04-28T07:05:13+09:00","level":"INFO","event":"parse_ok","status":"full"}
{"ts":"2026-04-28T07:05:13+09:00","level":"INFO","event":"no_change","prev":"full","curr":"full"}
{"ts":"2026-04-28T07:05:13+09:00","level":"INFO","event":"check_end","duration_ms":847}
```

## 10. セキュリティ

- `NTFY_TOPIC` は GitHub Secrets で管理。コードや設定ファイルにハードコードしない
- ログにトピック名を出力しない（マスキング推奨）
- リポジトリは Private 推奨。Public にする場合は state.json に個人情報を含めない（現設計では含まない）
- User-Agent はリポジトリURLを含める形を推奨（管理者からの問い合わせ窓口になる）
