# takachiho-watch

高千穂峡貸しボート予約サイトの **2026/5/8** の空き枠を監視し、
**状態が変化した瞬間のみ ntfy 経由でスマホへプッシュ通知**する GitHub Actions ベースのジョブ。

## ドキュメント構成

Claude Code に着手させる際は、以下の順で読ませる。

| 順 | ファイル | 内容 |
|---|---|---|
| 1 | `CLAUDE.md` | Claude Code 用プロジェクトインストラクション。最初に読ませる |
| 2 | `docs/requirements.md` | 要件書（What / Why） |
| 3 | `docs/specification.md` | 仕様書（How、技術設計） |
| 4 | `docs/harness-engineering.md` | ハーネス設計書（開発ループ、テスト、ロールアウト） |

## クイックスタート（実装後）

```bash
# 1. リポジトリ準備（Private 推奨）
gh repo create takachiho-watch --private

# 2. Secrets 設定
gh secret set NTFY_TOPIC                # 推測不能な文字列
gh secret set NTFY_TOPIC_TEST           # 動作確認用

# 3. ntfy アプリでトピックを購読
#    iOS/Android で ntfy.sh アプリ → Subscribe → トピック名入力

# 4. dry-run で動作確認
python scripts/check.py --dry-run

# 5. ワークフローを有効化
git push   # cron 起動
```
