# 05. 動画の取得

実装先: `src/priconne_cb_collector/adapters/youtube_rss.py`, `src/priconne_cb_collector/adapters/youtube_api.py`、
パイプラインは `src/priconne_cb_collector/services/collection.py`

2 経路を併用する。両方の結果は `video_id` でマージし、重複は 1 件として扱う（[07](07-persistence.md)）。

## 1. 経路A: チャンネル RSS（メイン）

```
https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}
```

- クォータ消費なし。`rss_interval_minutes` 間隔で全監視チャンネルを巡回
- 最新 15 件しか返らない点に注意。投稿頻度の高いチャンネルは間隔を詰める
- 取得できるのは `video_id` / `title` / `published` / `channel_title` のみ。**description・再生数・尺は取得できない**
- ETag / `If-Modified-Since` を使って 304 を活用する（ETag は `channel_etags` テーブルに保存）

## 2. 経路B: Data API v3 検索（サブ）

新規チャンネルの発掘用。`api_search_interval_hours` 間隔で実行。

```
GET https://www.googleapis.com/youtube/v3/search
  key, part=snippet, type=video, order=date, maxResults=50,
  regionCode=JP, relevanceLanguage=ja,
  publishedAfter={training_start - search_lookback_days},
  q="{search_query_base} {ボス名}"
```

- ボス 5 体それぞれで検索 → 1 巡 = 500 ユニット
- **`search.list` は 1 回 100 ユニット消費する。** 1 日の既定クォータは 10,000。3 時間間隔（1日8回 = 4,000ユニット）が上限の目安
- **EX表記（`ex1` 等）を検索クエリには使わない。** ノイズが多すぎるため（[06](06-classification.md) の EX表記判定は収集済み動画の分類にのみ使う）

## 3. 詳細情報の補完

RSS / 検索で得た `video_id` をまとめて `videos.list` に投げ、フィルタ用のメタデータを取得する。

```
GET https://www.googleapis.com/youtube/v3/videos
  key, part=snippet,contentDetails,statistics,liveStreamingDetails,
  id={最大50件のカンマ区切り}
```

- **`videos.list` は 50 件まとめて 1 ユニット。** 極めて安いので必ず経由すること
- ここで取れる `contentDetails.duration`（ISO 8601）でショート/長時間配信を除外
- `snippet.description` はここで初めて取得できる。判定ロジックはタイトルと説明文の両方を見る
- 配信中/配信予定のものは除外する。判定は次の OR:
  - `snippet.liveBroadcastContent` が `live` / `upcoming`
  - `liveStreamingDetails` があるのに `actualEndTime` が無い（＝まだ終わっていない）
- **配信終了済みのアーカイブ（`actualEndTime` あり）は除外しない。** 攻略アーカイブを丸ごと落としてしまうため

## 4. クォータ管理

- 消費ユニットは `quota_usage` テーブルに JST の日付単位で記録する
- `quota_limit_per_day` を超えそうな場合は **API 検索をスキップし、RSS のみで運用継続する。停止せず縮退動作させること**
- `quotaExceeded` エラーはリトライせず、その日の API 検索を停止して RSS のみに縮退する（[10](10-non-functional.md)）

| API | 1回あたりの消費 |
|---|---|
| チャンネル RSS | 0 |
| `search.list` | 100 |
| `videos.list`（50件まで） | 1 |
