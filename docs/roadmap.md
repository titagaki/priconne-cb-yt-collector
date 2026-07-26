# ロードマップ / 進捗管理

実装順序は [docs/spec/12-implementation-order.md](spec/12-implementation-order.md) に従う。
設計判断の記録は [docs/discussion/](discussion/README.md)。

## 進捗

すべて 2026-07-25 時点で完了。モジュール名は現構成（[02](spec/02-architecture.md)）で記載する。

| # | 項目 | 状態 |
|---|---|---|
| 0 | 未確定事項の決定・仕様反映 | ✅ 完了 |
| 1 | 設定読み込み + バリデーション + 収集期間（`adapters/config_file.py` / `domain/schedule.py`）+ テスト | ✅ 完了 |
| 2 | 判定ロジック（`domain/classify/`）+ 表形式テスト | ✅ 完了 |
| 3 | SQLite 永続化（`adapters/sqlite_store.py`）+ テスト | ✅ 完了 |
| 4 | 動画取得 → 判定 → DB 保存（`services/collection.py`） | ✅ 完了 |
| 5 | Discord 投稿（`interface/poster.py` / `interface/embeds.py`） | ✅ 完了 |
| 6 | Data API 検索 + クォータ管理（`adapters/youtube_api.py`） | ✅ 完了 |
| 7 | スラッシュコマンド + `interface/bot.py` / `cli.py` | ✅ 完了 |
| 8 | src レイアウトへの再編（domain / services / adapters / interface の4層化）+ ruff 導入 | ✅ 完了 |
| 9 | `tests/` を実装と同じ層構造に再編 + `PeriodService` の直接テスト追加 | ✅ 完了 |
| 10 | ドキュメント監査（実装先パスの更新、仕様と実装の食い違い4件の解消） | ✅ 完了 |
| 11 | 機能削減（2026-07-26）: フェーズ 3値 → 2値、段階抽出の削除、ポーリング間隔の統一 | ✅ 完了 |
| 12 | 機能削減（2026-07-26）: `/bosses` の削除、`schedule.mode` の廃止（`/start` / `/stop` のみ） | ✅ 完了 |
| 13 | 機能削減（2026-07-26）: RSS 監視の廃止、API 検索を全ボス1 OR クエリ・30分間隔へ | ✅ 完了 |
| 14 | 機能削減（2026-07-26）: 複数ボスヒットを判定不能へ一本化、バッジ3種の削除 | ✅ 完了 |

実装は一巡し、ユニットテスト 237 件が通っている状態。**Discord / YouTube への実接続は未検証**（トークン・API キー・投稿先チャンネル ID の設定が必要）。

## 機能削減（2026-07-26）

要件に無い機能を削除した。削除対象・理由・DB スキーマへの影響は
[discussion/削減の記録](discussion/reductions.md) を参照。

**既存の `data/bot.db` とは互換性がない。**移行スクリプトは用意していないので作り直すこと。

## 実接続で確認したいこと

- [ ] `/start` の確認ボタンからボス別スレッド5本が作成されること
- [ ] `/stop` が未投稿分を投げ切ってから収集件数サマリを出すこと（3秒の応答期限内に defer できているか）
- [ ] Embed のレイアウト（サムネイル、フッターの日時が JST）
- [ ] OR クエリの検索結果（5ボス分が 50 件の枠に収まるか、無関係な動画がどれだけ枠を食うか）
- [ ] `videos.list` のレスポンスで `duration` / `liveStreamingDetails` が期待どおり取れること
- [ ] 判定ログ（`logs/bot.jsonl`）を見て、エイリアスの過不足を運用者と調整する

## 運用開始前に必要な手作業

- [ ] `config/config.yaml` の `discord.channel_id` を実チャンネルに設定
- [ ] `.env` に `DISCORD_BOT_TOKEN` / `YOUTUBE_API_KEY` を設定
- [ ] 当月の `config/bosses.yaml` を記入（エイリアスは運用者が編集する）
