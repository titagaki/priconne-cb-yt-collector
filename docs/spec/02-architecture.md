# 02. 技術構成

## 1. 言語・ライブラリ

| 用途 | 採用 |
|---|---|
| 言語 | Python 3.11+ |
| Discord | discord.py 2.x |
| HTTP | httpx（非同期） |
| 永続化 | SQLite（標準 `sqlite3`。ORM は使わない） |
| 設定 | PyYAML |
| 環境変数 | python-dotenv |

タイムゾーンは Asia/Tokyo 固定。**DB には UTC で保存し、表示時に JST 変換する。**

## 2. ファイル構成

**層は分けない。**この規模では 1 ファイル 1 役で足りる。

```
src/priconne_cb_collector/
├── __main__.py       # python -m priconne_cb_collector
├── cli.py            # 起動：設定を読み、Bot を動かす
├── config.py         # config.yaml / bosses.yaml の読み込みと検証
├── youtube.py        # Data API v3（search.list のみ）
├── classify.py       # ボス名マッチと NG ワード判定（純粋関数）
├── store.py          # SQLite
├── bot.py            # 常駐ループ、投稿、スラッシュコマンド
└── logging_setup.py  # JSON Lines ログ

tests/                # 実装と 1:1（test_config / test_classify / test_store / test_bot）
config/               # config.yaml, bosses.yaml
data/                 # bot.db
logs/                 # bot.jsonl
```

`classify.py` は YouTube にも Discord にも依存しない純粋関数として書く。

## 3. DB スキーマ

**投稿に成功した動画だけを記録する。**投稿できなかった動画は記録されないので、
次の巡回で再び見つかり、自然に再試行される。取得中・投稿待ちといった状態は持たない。

```sql
-- 投稿済みの動画。重複投稿を防ぐのが主目的
CREATE TABLE posted_videos (
  video_id   TEXT PRIMARY KEY, -- YouTube の動画 ID。重複排除のキー
  title      TEXT NOT NULL,    -- 投稿時点のタイトル（ログ・集計用）
  boss_index INTEGER,          -- 1〜5。NULL = 判定不能（fallback へ投稿した）
  posted_at  TEXT NOT NULL,    -- 投稿に成功した時刻（ISO8601 UTC）
  cb_period  TEXT NOT NULL     -- "2026-07" 形式。/stop のサマリと /status の集計用
);

CREATE INDEX idx_posted_period ON posted_videos(cb_period);

-- 再起動をまたいで収集状態を復元するための記録
CREATE TABLE period_state (
  cb_period TEXT PRIMARY KEY,  -- "2026-07"（/start した時点の JST の月）
  start_at  TEXT,              -- /start の実行時刻（ISO8601 UTC）。終了日時は持たない
  is_open   INTEGER DEFAULT 0  -- 収集中か（/start で 1、/stop で 0）
);
```

**重複排除は `video_id` の PRIMARY KEY 制約のみで行う。** タイトル類似度による判定はしない。

収集中かどうかは `is_open` だけで判断する。開いている期間は常に高々1つ。

## 4. エラーハンドリング

- **1件の動画の処理失敗が収集ジョブ全体を落とさないこと。**動画ごとに try/except で囲み、
  失敗はログに残して次の動画へ進む。**失敗した動画は記録しない**ので次の巡回で再試行される
- YouTube API は指数バックオフで最大3回リトライする
- Discord が 429 を返したら `Retry-After` に従って待機し、同一動画につき最大3回まで再送する
- 設定ファイルが不正なら**起動を中止する**（`ConfigError`）

## 5. ログ

`logs/bot.jsonl` に JSON Lines、標準エラーにプレーンテキストで出す。

必ず INFO で残すもの:

| 場面 | 内容 |
|---|---|
| 検索 | クエリ、件数、消費ユニット |
| 投稿 | `video_id`、判定したボス、投稿先チャンネル、タイトル |
| NG ワード除外 | `video_id`、タイトル |
| 巡回の終了 | 見つけた件数、投稿した件数 |

**投稿したタイトルはログに残す。**`bosses.yaml` のエイリアスの過不足は、このログを見て調整する。

## 6. テスト

| 対象 | ケース |
|---|---|
| `classify.py` | ボス名一致、エイリアス一致、複数ヒット（＝判定不能）、ヒットなし、正規化（全角/半角/大小文字）、NG ワード |
| `store.py` | 投稿済みだけが記録されること、重複 INSERT が既存を壊さないこと、`is_open` が再起動をまたいで復元されること |
| `config.py` | 妥当な設定が読めること、不正な設定で `ConfigError` になること |
| `bot.py` | 投稿先の振り分け、重複投稿しないこと、NG 除外、投稿失敗が記録されず再試行されること、1件の失敗で巡回が止まらないこと |

ボス判定は**実際の動画タイトルを模したサンプルを 15 件以上用意した表形式のテスト**にする。
