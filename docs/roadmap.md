# ロードマップ / 進捗管理

実装順序は [docs/spec/12-implementation-order.md](spec/12-implementation-order.md) に従う。
未確定事項（11章）は **2026-07-25 に全5件決定済み**（既定 trigger + 催促 / EX折衷案採用 / 品質フィルタなし / 期間終了後は投げ切る / `/suggest_channels` 実装）。

## 進捗

すべて 2026-07-25 時点で完了。モジュール名は現構成（[02](spec/02-architecture.md)）で記載する。

| # | 項目 | 状態 |
|---|---|---|
| 0 | 未確定事項の決定・仕様反映 | ✅ 完了 |
| 1 | 設定読み込み + バリデーション + 期間判定（`adapters/config_file.py` / `domain/schedule.py`）+ テスト | ✅ 完了 |
| 2 | 判定ロジック（`domain/classify/`）+ 表形式テスト | ✅ 完了 |
| 3 | SQLite 永続化（`adapters/sqlite_store.py`）+ テスト | ✅ 完了 |
| 4 | RSS 取得 → 判定 → DB 保存（`adapters/youtube_rss.py` / `services/collection.py`） | ✅ 完了 |
| 5 | Discord 投稿（`interface/poster.py` / `interface/embeds.py`） | ✅ 完了 |
| 6 | Data API 検索 + クォータ管理（`adapters/youtube_api.py`） | ✅ 完了 |
| 7 | スラッシュコマンド（`/suggest_channels` 含む）+ `interface/bot.py` / `cli.py` | ✅ 完了 |
| 8 | src レイアウトへの再編（domain / services / adapters / interface の4層化）+ ruff 導入 | ✅ 完了 |
| 9 | `tests/` を実装と同じ層構造に再編 + `PeriodService` の直接テスト追加 | ✅ 完了 |

実装は一巡し、ユニットテスト 260 件が通っている状態。**Discord / YouTube への実接続は未検証**（トークン・チャンネル ID・実チャンネルの設定が必要）。

レイヤの依存方向（interface → services → adapters → domain の一方向、domain は外部ライブラリ非依存）は
`tests/test_layering.py` が AST 解析で機械的に検証している。

## 仕様と実装の食い違い（未解決）

2026-07-25 のドキュメント監査で検出。**いずれも実装側が仕様に届いていない**もので、コードは未修正。
どちらに寄せるか（実装を直すか仕様を緩めるか）を決めてから着手する。

| # | 内容 | 該当仕様 | 影響 |
|---|---|---|---|
| A | `polling.idle_check_interval_minutes` が実装で使われていない。tick は全フェーズ一律 60 秒 | [04](spec/04-schedule.md) §3 | 小。idle 中は DB 参照のみで通信しないが、設定項目が効かない |
| B | クォータ消費の**日次サマリ INFO ログ**が未実装。API 呼び出しごとのログも仕様は DEBUG だが実装は INFO | [10](spec/10-non-functional.md) §2 | 小。消費量の日次把握が `/status` 頼みになる |
| C | `/collect` を稼働期間外に実行すると `videos.discovered_phase` に `"idle"` が入る。仕様上の定義域は `training` / `battle` | [07](spec/07-persistence.md) §1 | 小。トレモ判定は「根拠なし」に倒れるだけで誤判定はしない |
| D | 日次投稿上限の到達通知が**プロセス起動中に1回だけ**。日付が変わって再度上限に達しても通知されない（フラグは期間終了時にしかリセットされない） | [08](spec/08-discord-posting.md) §3 | 中。2日目以降、投稿が止まっていることに気付きにくい |

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
