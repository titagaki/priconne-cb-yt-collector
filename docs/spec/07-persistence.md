# 07. 永続化（SQLite）

実装先: `src/priconne_cb_collector/adapters/sqlite_store.py`（DB ファイルは `data/bot.db`）

判断の理由は [`docs/discussion/`](../discussion/README.md) を参照。

日時はすべて **ISO8601 UTC で保存し、表示時に JST 変換**する（[02](02-architecture.md)）。ただし `quota_usage.date` のみ JST の日付。

## 1. スキーマ

```sql
CREATE TABLE videos (
  video_id        TEXT PRIMARY KEY,
  title           TEXT NOT NULL,
  description     TEXT,
  channel_id      TEXT NOT NULL,
  channel_title   TEXT,
  published_at    TEXT NOT NULL,   -- ISO8601 UTC
  duration_sec    INTEGER,
  view_count      INTEGER,
  discovered_at   TEXT NOT NULL,

  boss_index      INTEGER,         -- NULL = 判定不能（複数ボスにヒットした場合を含む）
  match_source    TEXT,            -- boss_index を決めた経路。判定不能なら NULL
                                   --   "boss_name"   … bosses.yaml の name/aliases に一致
                                   --   "ex_notation" … 「EX3」等の番号表記からの推定（確度が低い）

  battle_type     TEXT,            -- "normal" | "carryover" | "unknown"
  carryover_sec   INTEGER,
  damage          INTEGER,         -- 万単位に正規化

  status          TEXT NOT NULL,   -- "pending" | "posted" | "filtered" | "error"
  filter_reason   TEXT,
  posted_at       TEXT,
  discord_msg_id  TEXT,
  cb_period       TEXT NOT NULL    -- "2026-07" 形式。期間ごとの集計用
);

CREATE INDEX idx_videos_status ON videos(status);
CREATE INDEX idx_videos_period_boss ON videos(cb_period, boss_index);

-- 開始 / 終了通知の重複投稿を防ぐための状態管理
CREATE TABLE period_state (
  cb_period            TEXT PRIMARY KEY,  -- "2026-07"（/start した時点の JST の月）
  start_at             TEXT,              -- /start の実行時刻。終了日時は持たない
  notified_start       INTEGER DEFAULT 0,
  notified_end         INTEGER DEFAULT 0,
  boss_thread_ids      TEXT,              -- {boss_index: thread_id} の JSON
  is_open              INTEGER DEFAULT 0  -- 収集中か（/start で 1、/stop で 0）
);

CREATE TABLE quota_usage (
  date        TEXT PRIMARY KEY,    -- JST の日付
  units_used  INTEGER NOT NULL DEFAULT 0
);
```

**判定結果のうち DB に残すのは投稿の見た目と振り分けに使う値だけ。**ヒットしたボスが複数だった
場合の内訳やマッチした文字列はログにのみ残す（[06](06-classification.md) §2、[10](10-non-functional.md) §2）。

## 2. 重複排除

**重複排除は `video_id` の PRIMARY KEY 制約のみで行う。** `INSERT OR IGNORE` を使い、既存レコードがあれば投稿処理をスキップする。

タイトル類似度による重複判定は行わない。

## 3. `status` の遷移

| 値 | 意味 |
|---|---|
| `pending` | 収集済み・投稿待ち |
| `posted` | Discord へ投稿成功（**投稿成功時のみ**更新する。[08](08-discord-posting.md)） |
| `filtered` | 除外フィルタ・日次上限に該当。`filter_reason` に理由を記録 |
| `error` | 判定・投稿で個別エラー（ジョブ全体は落とさない。[10](10-non-functional.md)） |
