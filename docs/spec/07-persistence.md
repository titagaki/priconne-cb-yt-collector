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
  discovered_via  TEXT NOT NULL,   -- "rss" | "api_search"
  discovered_at   TEXT NOT NULL,

  boss_index      INTEGER,         -- NULL = 判定不能
  boss_indices    TEXT,            -- 複数ヒット時の JSON 配列
  match_source    TEXT,            -- "boss_name" | "ex_notation"
  is_summary      INTEGER DEFAULT 0,

  battle_type     TEXT,            -- "normal" | "carryover" | "unknown"
  carryover_sec   INTEGER,
  damage          INTEGER,
  is_full_auto    INTEGER,
  is_manual       INTEGER,
  is_training_footage INTEGER,     -- トレモ動画と判定されたか（キーワード由来のみ）

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

CREATE TABLE channel_etags (
  channel_id  TEXT PRIMARY KEY,
  etag        TEXT,
  last_fetch  TEXT
);
```

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
