# 07. 永続化（SQLite）

実装先: `src/priconne_cb_collector/adapters/sqlite_store.py`（DB ファイルは `data/bot.db`）

判断の理由は [`docs/discussion/`](../discussion/README.md) を参照。

日時はすべて **ISO8601 UTC で保存し、表示時に JST 変換**する（[02](02-architecture.md)）。ただし `quota_usage.date` のみ JST の日付。

## 1. スキーマ

```sql
-- 収集した動画。1本につき1行で、投稿済みかどうかもここで管理する
CREATE TABLE videos (
  -- YouTube から取得した値
  video_id        TEXT PRIMARY KEY, -- YouTube の動画 ID。重複排除のキー（§2）
  title           TEXT NOT NULL,    -- 動画タイトル。判定の入力かつ Embed の表示に使う
  description     TEXT,             -- 説明文。全文を保存するが、判定に使うのは先頭500文字
                                    --   （[06](06-classification.md)）。Embed には転載しない
  channel_id      TEXT NOT NULL,    -- 投稿チャンネルの ID
  channel_title   TEXT,             -- 投稿チャンネル名。Embed のフッターに出す
  published_at    TEXT NOT NULL,    -- 動画の投稿日時（ISO8601 UTC）。EX表記の適用判定にも使う
  duration_sec    INTEGER,          -- 長さ（秒）。短すぎ / 長すぎの除外フィルタに使う
  view_count      INTEGER,          -- 再生数。取得・保存しているが未使用
  discovered_at   TEXT NOT NULL,    -- Bot がこの動画を見つけた時刻（ISO8601 UTC）

  -- 判定結果（[06](06-classification.md)）
  boss_index      INTEGER,          -- 1〜5。NULL = 判定不能（複数ボスにヒットした場合を含む）
  match_source    TEXT,             -- boss_index を決めた経路。判定不能なら NULL
                                    --   "boss_name"   … bosses.yaml の name/aliases に一致
                                    --   "ex_notation" … 「EX3」等の番号表記からの推定（確度が低い）
  battle_type     TEXT,             -- "normal" | "carryover" | "unknown"
  carryover_sec   INTEGER,          -- 持ち越し秒数（1〜90）。battle_type = "carryover" かつ
                                    --   秒数を読み取れたときのみ。範囲外は捨てて NULL
  damage          INTEGER,          -- 与ダメージ。万単位に正規化（1.5億 → 15000）

  -- 投稿の状態（§3）
  status          TEXT NOT NULL,    -- "pending" | "posted" | "filtered" | "error"
  filter_reason   TEXT,             -- status = "filtered" の理由。それ以外は NULL
                                    --   "too_short" | "too_long" | "live" | "ng_word"
                                    --   | "boss_unknown"（[06](06-classification.md) §5）
                                    --   | "daily_limit"（[08](08-discord-posting.md) §3）
  posted_at       TEXT,             -- 投稿に成功した時刻（ISO8601 UTC）。未投稿なら NULL
  discord_msg_id  TEXT,             -- 投稿した Discord メッセージの ID。数値だが文字列で持つ
  cb_period       TEXT NOT NULL     -- "2026-07" 形式。期間ごとの集計用
);

CREATE INDEX idx_videos_status ON videos(status);          -- 未投稿分の取り出し
CREATE INDEX idx_videos_period_boss ON videos(cb_period, boss_index);  -- ボス別の集計・日次上限

-- 再起動をまたいで収集状態を復元するための記録。収集期間ごとに1行
CREATE TABLE period_state (
  cb_period            TEXT PRIMARY KEY,  -- "2026-07"（/start した時点の JST の月）
  start_at             TEXT,              -- /start の実行時刻。終了日時は持たない
  boss_thread_ids      TEXT,              -- {boss_index: thread_id} の JSON。
                                          --   再起動時にスレッドを作り直さないため
  is_open              INTEGER DEFAULT 0  -- 収集中か（/start で 1、/stop で 0）。
                                          --   再起動時はこれだけを見て再開する
);

-- YouTube API の消費ユニット。上限を超えそうな検索をスキップするために使う
CREATE TABLE quota_usage (
  date        TEXT PRIMARY KEY,          -- JST の日付。JST 0時にリセットされる
  units_used  INTEGER NOT NULL DEFAULT 0 -- その日に消費したユニット数の累計
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
