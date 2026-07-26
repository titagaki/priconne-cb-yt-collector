# 削減の記録

実装が一巡したあと、要件に無い機能を削除した記録。

## 2026-07-26: RSS 監視の廃止（取得は API 検索 1 本）

運用者の判断による。理由と代償は [動画の取得](collection.md#rss-監視をやめapi-検索-1-本にした理由)。

| 削除したもの | 備考 |
|---|---|
| `adapters/youtube_rss.py` | チャンネル RSS 取得。feedparser 依存ごと削除 |
| `youtube.channels` 設定と `ChannelRef` | 監視先リスト |
| `channel_etags` テーブルと `get_etag` / `save_etag` | ETag による 304 スキップ |
| `/suggest_channels` と `channel_hit_counts` | RSS 監視候補の提案。追加先が無くなった |
| `videos.discovered_via` | 経路が1つになり常に同じ値になった |
| `polling.rss_interval_minutes` / `api_search_interval_hours` | `search_interval_minutes`（既定30）に統合 |
| `/collect` の `api_search` 引数 | 検索しかないので選択肢にならない |

### 併せて変更した点

- **全ボス名を1つの OR クエリにまとめた。**`search.list` は結果件数によらず 1 回 100 ユニット
  固定なので、ボスごとに投げると 1 巡 500 ユニットで 80 分間隔が限界だった。
  まとめることで 1 巡 100 ユニットになり、RSS と同じ 30 分間隔を維持できる
- **`YOUTUBE_API_KEY` を必須にした。**以前は未設定でも RSS だけで動いたが、
  いまは何も収集できないので起動を中止する

### クォータの見積もり

```
検索      100ユニット × 48巡/日 = 4,800
videos.list                    ≈ 数十
--------------------------------------
合計                           ≈ 4,800 / 日（上限 9,000）
```

変更前は 4,000/日（500 × 8巡）だったので、**消費は約 800 ユニット増**。
そのぶん新着への追従が 3 時間から 30 分に縮まった。

### 挙動が変わった点

- **無関係な動画の混入率が上がる。**「監視対象がプリコネ実況者のチャンネルなので
  他ゲームの動画が入りにくい」という緩和要因が消えた。`title_ng_words` の調整が
  唯一の対策になる（[判定ロジックの実測値](collection.md#代償-無関係な動画が大量に混ざる)）
- `maxResults=50` を全ボスで共有するため、1 巡で 50 件を超える新着があると取りこぼす
- クォータ超過時の「RSS のみに縮退」が無くなり、その時間帯の動画は取りこぼす

### DB スキーマへの影響

`videos.discovered_via` 列と `channel_etags` テーブルを削除した。**既存の
`data/bot.db` とは互換性がない**（下記 `mode` 廃止と同じ扱いで、作り直す前提）。

## 2026-07-26: `schedule.mode` の廃止（収集は `/start` と `/stop` だけ）

運用者の判断による。「モードという概念が煩わしい」という理由で、収集期間を日付から
決める仕組みを全廃した。理由の詳細は [収集期間](schedule.md#mode-を廃止した理由)。

| 削除したもの | 備考 |
|---|---|
| `schedule.mode`（`offset` / `manual` / `trigger`） | 起動は `/start` のみ |
| `start_offset_days` / `end_offset_days` | 末日基準のオフセット計算そのもの |
| `manual_start` / `manual_end` と `/period set` | 日付の手動上書き |
| 終了日（`Period.end`） | `/stop` されるまで終わらない |
| `remind_if_not_started` と `/start` 催促 | 催促日を算出する根拠（offset 式）が消えた |
| `polling.idle_check_interval_minutes` | 待機中はループ自体を回さない |
| `ScheduleConfig` | 中身が空になった。`search_lookback_days` は `youtube` へ移動 |

結果として `config.yaml` から `schedule:` セクションが丸ごと消えた。

### 挙動が変わった点

- **収集は自動で終わらない。**`/stop` を忘れると翌月まで回り続け、クォータを消費する
- `/stop` が収集終了通知（ボス別サマリ）を出すようになった。以前は期間終了の遷移が出していた
- `bosses.yaml` の `month` 検証を、現在の月ではなく `cb_period` と比較するようにした。
  月末に開始した収集が日付をまたいだ瞬間に止まらないようにするため
- 同じ月に `/start` し直すと開始通知を再度出す（プロセス再起動のときだけ黙る）

### DB スキーマへの影響

`period_state` から `end_at` と `notified_reminder` を削除し、`started_manually` を
`is_open` に改名した。開始経路が1つになり「手動で」という限定が意味を失ったため。

**既存の `data/bot.db` とは互換性がない。** 実運用前のため移行スクリプトは用意せず、
DB ファイルを作り直す前提とした（下記 2026-07-26 の削減と同じ扱い）。

## 2026-07-26: `/bosses` コマンドの削除

運用者の判断による。`/status` が収集期間中に全ボスを「Nボス ボス名: X件」の形で
（0件のボスも省略せず）並べるため、ボス一覧を見る用途は `/status` で足りる。

ボス構成の Embed（`build_bosses_embed`）自体は残す。`/start` の確認ステップと
`/reload` の結果表示で使っており、こちらは**エイリアスと `month` 不一致の警告**まで出す。
`/status` はボス名と件数しか出さないので、エイリアスを確認したいときは `/reload` を使う。

## 2026-07-26: フェーズの2値化と段階の削除

運用者の判断による。実装 3,025行 / テスト 2,186行の状態からの削減。

| 削除したもの | 理由 |
|---|---|
| トレモ期間 / 本番期間の区別（3状態 → 2状態） | [収集期間](schedule.md#状態を収集する--しないの2値にした理由) |
| ボスの「段階」抽出（`boss_phase`） | [判定ロジック](classification.md#ボスの段階) |
| `training_evidence` の2値（`keyword` / `phase_only`） | 期間の区別が消えて `phase_only` が成立しなくなった。`is_training_footage: bool` に集約 |
| 本番開始通知 | 運用者はゲーム内で本番開始を知っている |
| ポーリング間隔の期間別分岐（設定5項目 → 3項目） | 上記に伴い統一。RSS 30分 / API 検索 3時間（後に検索30分へ統合） |
| `schedule.training_days_before` | `start_offset_days` に統合（5 + 3 → 8）。計算結果は不変 |
| `manual_training_start` / `manual_battle_start` | `manual_start` に統合 |

### DB スキーマへの影響

削除された列:

- `videos.discovered_phase` / `videos.boss_phase` / `videos.training_evidence`
- `period_state.battle_start` / `period_state.notified_battle`

改名された列:

- `period_state.training_start` → `start_at`、`period_state.battle_end` → `end_at`
- `period_state.notified_training` → `notified_start`

**既存の `data/bot.db` とは互換性がない。** 実運用前のため移行スクリプトは用意せず、
DB ファイルを作り直す前提とした。

### 検討したが削除しなかったもの

| 候補 | 残した理由 |
|---|---|
| ETag / 304 対応 | 実装コストが小さく、無駄な取得を減らす実利がある（**2026-07-26 に RSS ごと廃止**） |
| 429 リトライ | レート制限時の取りこぼし耐性。目的に直結する |
| `damage` / `is_full_auto` / `is_manual` の抽出 | 段階と違い、動画を選ぶ判断材料として機能している |
| 待機中のポーリングループ | 止めると `offset`/`manual` の自動開始と `/start` 催促が同時に死ぬ（**2026-07-26 に両方とも廃止され、ループも停止**）。[収集期間](schedule.md#待機中はポーリングループを回さない) |

### まだ判断していない削減候補

以下は候補として挙げたが、採否を決めていない。

- 設定フラグの固定値化（`layout` の `single`、`enable_ex_notation`、`on_boss_unknown`）
- `/recent` / `/collect` / `/stop` / `/reload` の整理
- `videos.view_count`（取得・保存しているが未使用）
- まとめ動画の `is_summary` 別扱い
