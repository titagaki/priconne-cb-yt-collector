# ロードマップ / 進捗管理

実装順序は [docs/spec/12-implementation-order.md](spec/12-implementation-order.md) に従う。
未確定事項（11章）は **2026-07-25 に全5件決定済み**（既定 trigger + 催促 / EX折衷案採用 / 品質フィルタなし / 期間終了後は投げ切る / `/suggest_channels` 実装）。

## 進捗

| # | 項目 | 状態 |
|---|---|---|
| 0 | 未確定事項の決定・仕様反映 | ✅ 完了（2026-07-25） |
| 1 | 設定読み込み + バリデーション + 期間判定（`config.py` / `schedule.py`）+ テスト | ✅ 完了 |
| 2 | 判定ロジック（`classify/`）+ 表形式テスト | ✅ 完了 |
| 3 | SQLite 永続化（`store.py`）+ テスト | ✅ 完了 |
| 4 | RSS 取得 → 判定 → DB 保存（`sources/rss.py` / `collector.py`） | ✅ 完了 |
| 5 | Discord 投稿（`discord_bot/poster.py`） | ✅ 完了 |
| 6 | Data API 検索 + クォータ管理（`sources/youtube_api.py`） | ✅ 完了 |
| 7 | スラッシュコマンド（`/suggest_channels` 含む）+ `main.py` | ✅ 完了 |

| 8 | src レイアウトへの再編（domain / services / adapters / interface の4層化）+ ruff 導入 | ✅ 完了（2026-07-25） |

実装は一巡し、ユニットテスト 239 件が通っている状態。**Discord / YouTube への実接続は未検証**（トークン・チャンネル ID・実チャンネルの設定が必要）。

レイヤの依存方向（interface → services → adapters → domain の一方向、domain は外部ライブラリ非依存）は
`tests/test_layering.py` が AST 解析で機械的に検証している。

## 実接続で確認したいこと

- [ ] `/start` の確認ボタンからボス別スレッド5本が作成されること
- [ ] Embed のレイアウト（サムネイル、バッジ、フッターの日時が JST）
- [ ] 実際の RSS フィードのパース（`published` の書式、ETag による 304）
- [ ] `videos.list` のレスポンスで `duration` / `liveStreamingDetails` が期待どおり取れること
- [ ] 判定ログ（`logs/bot.jsonl`）を見て、エイリアスの過不足を運用者と調整する

## 運用開始前に必要な手作業

- [ ] `config/config.yaml` の `youtube.channels` に実チャンネル ID を設定（11-5）
- [ ] `config/config.yaml` の `discord.channel_id` を実チャンネルに設定
- [ ] `.env` に `DISCORD_BOT_TOKEN` / `YOUTUBE_API_KEY` を設定
- [ ] 当月の `config/bosses.yaml` を記入（エイリアスは運用者が編集する）
