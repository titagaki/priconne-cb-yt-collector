# 05. 動画の取得

実装先: `src/priconne_cb_collector/adapters/youtube_api.py`、
パイプラインは `src/priconne_cb_collector/services/collection.py`

判断の理由は [discussion/動画の取得](../discussion/collection.md) を参照。

取得経路は **Data API v3 の検索 1 本のみ**。RSS によるチャンネル監視は行わない。

## 1. Data API v3 検索

`search_interval_minutes`（既定 30 分）間隔で 1 回だけ実行する。

```
GET https://www.googleapis.com/youtube/v3/search
  key, part=snippet, type=video, order=date, maxResults=50,
  regionCode=JP, relevanceLanguage=ja,
  publishedAfter={収集開始 - search_lookback_days},
  q="{ボス1} OR {ボス2} OR {ボス3} OR {ボス4} OR {ボス5}"
```

- **`bosses.yaml` の全ボス名を 1 つの OR クエリにまとめる。**`search.list` は結果件数に
  かかわらず 1 回 100 ユニット固定なので、1 巡 = 100 ユニットになる
- **クエリはボス名のみ。**「プリコネ」「クラバト」を足さない（[06](06-classification.md) の対象にはこれらを含まないタイトルが多いため）
- エイリアスは検索クエリに使わない。エイリアスは [06](06-classification.md) のボス判定にのみ使う
- **EX表記（`ex1` 等）を検索クエリには使わない。** [06](06-classification.md) の EX表記判定は収集済み動画の分類にのみ使う
- `maxResults=50` の枠を全ボスで共有するため、1 巡で 50 件を超える新着があると取りこぼす
- 検索が失敗しても収集ジョブは落とさない。次の巡回で拾い直す

## 2. 詳細情報の補完

検索で得た `video_id` をまとめて `videos.list` に投げ、フィルタ用のメタデータを取得する。

```
GET https://www.googleapis.com/youtube/v3/videos
  key, part=snippet,contentDetails,statistics,liveStreamingDetails,
  id={最大50件のカンマ区切り}
```

- **`videos.list` は 50 件まとめて 1 ユニット。** 収集した動画は必ずここを経由させる
- DB に既知の `video_id` は先に除外してから投げる
- ここで取れる `contentDetails.duration`（ISO 8601）でショート/長時間配信を除外
- `snippet.description` は検索結果では切り詰められる。判定に使うのはここで得た全文
- 配信中/配信予定のものは除外する。判定は次の OR:
  - `snippet.liveBroadcastContent` が `live` / `upcoming`
  - `liveStreamingDetails` があるのに `actualEndTime` が無い（＝まだ終わっていない）
- **配信終了済みのアーカイブ（`actualEndTime` あり）は除外しない**

## 3. クォータ管理

- 消費ユニットは `quota_usage` テーブルに JST の日付単位で記録する
- `quota_limit_per_day` を超えそうな場合は **検索をスキップする。Bot は停止しない**
- `quotaExceeded` エラーはリトライせず、その日の検索を止める（[10](10-non-functional.md)）
- 検索をスキップした場合も収集ジョブ自体は停止しない。次の巡回で再度判定する

| API | 1回あたりの消費 |
|---|---|
| `search.list` | 100（結果件数によらず固定） |
| `videos.list`（50件まで） | 1 |

既定（30分間隔）での1日あたりの見積もり:

```
検索      100ユニット × 48巡 = 4,800
videos.list                  ≈ 数十
------------------------------------
合計                         ≈ 4,800 / 日（上限 9,000）
```

**検索が唯一の取得経路なので、`YOUTUBE_API_KEY` は必須。**未設定なら起動を中止する。
