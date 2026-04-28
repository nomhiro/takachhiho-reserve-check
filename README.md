# takachiho-watch

高千穂峡貸しボート予約サイト（`https://eipro.jp/takachiho1/eventCalendars/index`）の **2026/5/8** の空き枠を 1 時間ごとに監視し、**状態が変化した瞬間だけ** ntfy 経由でスマホへプッシュ通知する GitHub Actions ジョブ。

## 仕組み

- 1 時間に 1 回（毎時 5 分）GitHub Actions が起動
- サイトの内部 JSON API (`POST /takachiho1/eventCalendars/search`) を叩いて 5/8 のエントリを取得
- `ordable: true` なら **空きあり**、`false` または該当エントリ無しなら **満室**
- 直前の状態（`state/state.json`）と比較し、変化したら ntfy.sh にプッシュ送信
- 7:00 JST 以降の最初の実行で、その日のヘルスチェック通知（low）を送信
- state.json は変化があれば自動で `chore(state): update at ...` としてコミット&push
- **5/7 を最終監視日**とし、5/8 以降は自動停止

## ドキュメント構成

| 順 | ファイル | 内容 |
|---|---|---|
| 1 | [`CLAUDE.md`](./CLAUDE.md) | プロジェクトインストラクション |
| 2 | [`docs/requirements.md`](./docs/requirements.md) | 要件書（What / Why） |
| 3 | [`docs/specification.md`](./docs/specification.md) | 仕様書（How、技術設計） |
| 4 | [`docs/harness-engineering.md`](./docs/harness-engineering.md) | ハーネス設計書（開発ループ・テスト・ロールアウト） |

## 通知の種類

| 状態遷移 | Priority | Tag | タイトル例 |
|---|---|---|---|
| 満室 → **空きあり** | urgent | rotating_light, boat | 🚨 高千穂峡 5/8 空き検知！ |
| 空きあり → 満室 | default | x | 高千穂峡 5/8 満室に戻りました |
| 連続3回失敗 | high | warning | ⚠️ takachiho-watch エラー |
| エラー復旧（→ 満室） | low | white_check_mark | 高千穂峡 5/8 監視復旧（満室） |
| 毎日 7:00 JST | low | white_check_mark | takachiho-watch 稼働中 |

## クイックスタート

### 1. リポジトリを Private で作成

```bash
gh repo create takachiho-watch --private --source=. --push
```

### 2. ntfy アプリで購読するトピックを決める

- **推測困難な十分長い文字列**にする（例: `mySecretBoatTopic-3f7a921bc8`）
- iOS / Android で `ntfy.sh` アプリをインストール → Subscribe → そのトピックを入力
- 同じトピックをテスト用にもう1つ用意する

### 3. GitHub Secrets を設定

```bash
# 本番トピック
gh secret set NTFY_TOPIC

# Phase 2 用テストトピック（任意。手動 dry-run/E2E に使用）
gh secret set NTFY_TOPIC_TEST
```

### 4. ローカルで dry-run（通知は送らない）

```bash
pip install -r requirements.txt
python -m scripts.check --dry-run
```

`state/state.json` が生成され、ログに `parse_ok` / `check_end` が出れば成功。

### 5. テストトピックで E2E（任意）

```bash
NTFY_TOPIC=$NTFY_TOPIC_TEST python -m scripts.check
# → スマホに通知が届くか確認（state を手動でいじって全パターンを試す）
```

### 6. ワークフローを有効化

`git push` するだけで cron が起動する。最初は `Actions` タブから `workflow_dispatch` で `dry_run=true` で 3 回ほど手動実行して挙動を確認するとよい。

## 段階的ロールアウト

| Phase | 内容 | 終了条件 |
|---|---|---|
| **0: 準備** | リポジトリ・Secrets・ntfy アプリ | テスト送信が届く |
| **1: dry-run** | `workflow_dispatch` で `dry_run=true` 手動実行 | 3 回連続で正しい状態判定がログに出る |
| **2: テストトピック** | `NTFY_TOPIC` をテスト用に設定し cron 有効化 | 24 時間動かして異常なし、ヘルスチェック通知到達 |
| **3: 本番** | `NTFY_TOPIC` を本番用トピックに切り替え | 5/8 まで継続稼働 |

**いきなり本番トピックに送らない。** Phase 1 → 2 → 3 を順に踏むこと。

## 運用

### 状態の見える化

`state/state.json` の git 履歴がそのまま監視ログ:

```bash
git log --oneline state/state.json
git log -p state/state.json   # 状態遷移の差分
```

### Actions ログ

GitHub の Actions UI で各実行の構造化ログ（JSON Lines）が確認できる。
`event` フィールドで `check_start` / `fetch_ok` / `parse_ok` / `notification_dispatch` / `check_end` を追える。

### ヘルスチェック未着のとき

毎週日曜の通知が届かない場合は、**Actions の cron が止まっている可能性**がある:

1. GitHub の Actions タブで watch ワークフローの最終実行を確認
2. 失敗していれば原因を確認（サイト側の API 仕様変更が最有力）
3. 60 日無コミットでの自動停止は、state.json の自動コミットで起こりにくいが念のためチェック

## トラブルシューティング

| 症状 | 原因候補 | 対処 |
|---|---|---|
| `parse_ok` が出ず `check_failed` が続く | サイトの API レスポンス仕様が変わった | `tests/fixtures/` に新形式を保存し parser 修正 |
| Actions がエラーで止まる | `permissions: contents: write` が無い／state ブランチ保護 | リポジトリ設定で Actions に push 権限付与 |
| 通知が届かない | トピック名間違い／ntfy.sh 障害 | `NTFY_TOPIC` を再確認、`https://ntfy.sh/<topic>` を curl で叩く |
| 毎時 0 分に重なって遅延 | `cron: '5 * * * *'` で対策済み | NFR-04 を許容（最大 75 分） |

## 撤収（5/8 経過後）

```bash
gh workflow disable watch.yml
# またはリポジトリごとアーカイブ
gh repo archive
```

ntfy トピックの購読はスマホアプリから手動で解除。

## 開発

```bash
# テスト
python -m pytest

# 個別テスト
python -m pytest tests/test_state_machine.py -v

# dry-run（実サイトに当てる）
python -m scripts.check --dry-run --target-date 2026-05-08
```

### ファイル構成

```
.
├── .github/workflows/watch.yml
├── docs/                       # 要件・仕様・ハーネス設計
├── scripts/
│   ├── check.py                # エントリポイント
│   ├── fetcher.py              # JSON API 取得（リトライ付き）
│   ├── parser.py               # 5/8 状態抽出
│   ├── notifier.py             # ntfy POST
│   ├── state.py                # state.json + 状態遷移ロジック
│   └── log.py                  # JSON Lines ログ
├── state/state.json            # 監視ログを兼ねる
├── tests/
│   ├── fixtures/               # JSON サンプル（available/full/error/missing_target）
│   └── test_*.py               # 52 ケース
└── requirements.txt
```

## セキュリティ

- `NTFY_TOPIC` は **必ず** GitHub Secrets で管理。コードや設定ファイルにハードコードしない
- ログにトピック名は出力しない（コードで意図的にマスク済み）
- リポジトリは **Private 推奨**
- ntfy.sh は認証不要なため、トピック名を知る者は誰でもメッセージを送信できる。十分推測困難な文字列を使うこと
