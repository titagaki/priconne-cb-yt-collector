# 削減の記録

実装が一巡したあと、要件に無い機能を削除した記録。

## 2026-07-26: 全面的な作り直し（6,001行 → 最小構成）

運用者の判断による。**「やりたいのは動画のリストをとってきて投稿するだけ。
おまけで Discord に投げる機能がつくだけ」**という原点の再確認から。

### きっかけ

運用者が書いた元のスクリプト `ytyt.py`（63行）と、実装（src 2,414行 / tests 1,860行 /
docs 1,727行 = 6,001行）を突き合わせた。**約95倍。**内訳を出すと、膨らんだ場所がはっきりした。

| 用途 | 行数 | 判断 |
|---|---:|---|
| Discord（常駐 Bot・コマンド6個・スレッド管理・投稿キュー・Embed） | 780 | ほぼ全部が作り込み |
| 永続化（3テーブル・22列） | 313 | 重複排除に要るのは `video_id` だけ |
| 収集パイプライン | 268 | 判定と除外を外せば数十行 |
| 判定ロジック | 280 | **ボス別スレッドに振り分けるためだけに存在していた** |
| YouTube 取得 | 175 | ここだけが `ytyt.py` と同じ仕事 |
| 設定2ファイル＋検証 | 200 | 項目を削れば大半消える |
| 収集期間 | 120 | 縮む |
| その他 | 245 | 縮む |

**ボス名は検索クエリにすでに入っている。**取ってきた動画を再度ボス名で判定していたのは、
ボス別スレッドへ振り分けるためだけだった。

### 運用者が決めたこと

| 論点 | 決定 |
|---|---|
| 実行形態 | **常駐 Bot のまま**中身を絞る（cron + Webhook 案は採らない） |
| 投稿先 | **ボスごとのチャンネルは残す。ただし Bot は作らない**。既存チャンネルを設定で指定する |
| 除外フィルタ | **NG ワードだけ残す**（尺・配信の判定は捨てる） |

### 削除したもの

| 削除したもの | 理由 |
|---|---|
| スレッドの自動作成・実在確認・復元 | 既存チャンネルを設定で指定する形にした。`period_state.boss_thread_ids` ごと不要 |
| `videos.list` によるエンリッチ | 尺・配信の判定をやめたので呼ぶ理由が消えた。取得は `search.list` 1本 |
| 尺フィルタ / 配信フィルタ | 上記。混ざったら目で飛ばす |
| クォータ管理（`quota_usage` テーブル一式） | `search.list` だけなら 30分間隔で 4,800/日。上限 10,000 に対して計算するまでもない |
| 投稿キュー（`pending` → `posted` の状態管理） | 取得したその場で投稿すれば状態が要らない。**投稿に成功した動画だけ記録する**ことで、失敗分は次の巡回で自然に再試行される |
| `videos.status` / `filter_reason` / `error` 行 | 上記に伴い不要 |
| 日次上限（`max_posts_per_boss_per_day`）と上限通知 | 1巡50件が上限なので溢れない |
| Embed | URL を貼れば Discord が自動でカード展開する |
| EX表記・持ち越し・ダメージの判定 | ボス名マッチだけ残せば投稿先は決まる |
| `layout` / `on_boss_unknown` / `enable_ex_notation` の設定 | 分岐そのものが消えた |
| `/collect` / `/recent` / `/reload` | `/start` `/stop` `/status` だけ残す |
| 4層のディレクトリ構成（domain / adapters / services / interface） | 400行台の実装に層は過剰。フラットな構成にした |

### 残したもの

| 残したもの | 理由 |
|---|---|
| 常駐 Bot と `/start` `/stop` | 運用者の決定。収集期間を Discord から制御できる |
| `/status` | 収集中かどうかを確認する唯一の手段。15行程度 |
| ボス名マッチ（エイリアス込み） | 投稿先チャンネルを決めるために要る |
| NG ワード除外 | タイトルの文字列マッチだけで済み、ガチャ・雑談動画に効く |
| `bosses.yaml` の月チェックと `/start` の確認ステップ | 先月の構成のまま回る事故は実害が大きい |
| 重複排除（`video_id`） | これが無いと毎巡同じ動画を投稿する |

### DB スキーマ

2テーブル・8列まで縮小した。

```sql
CREATE TABLE posted_videos (   -- 投稿に成功した動画だけ
  video_id   TEXT PRIMARY KEY,
  title      TEXT NOT NULL,
  boss_index INTEGER,
  posted_at  TEXT NOT NULL,
  cb_period  TEXT NOT NULL
);
CREATE TABLE period_state (
  cb_period TEXT PRIMARY KEY,
  start_at  TEXT,
  is_open   INTEGER DEFAULT 0
);
```

**既存の `data/bot.db` とは互換性がない。** DB ファイルを作り直す前提。

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
- 同じ月に `/start` し直すと開始通知を再度出す（プロセス再起動のときだけ黙る。
  **開始通知は後に `/start` の返信へ統合された**）

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
| `damage` / `is_full_auto` / `is_manual` の抽出 | 段階と違い、動画を選ぶ判断材料として機能している（**`is_full_auto` / `is_manual` は 2026-07-26 に廃止**） |
| 待機中のポーリングループ | 止めると `offset`/`manual` の自動開始と `/start` 催促が同時に死ぬ（**2026-07-26 に両方とも廃止され、ループも停止**）。[収集期間](schedule.md#待機中はポーリングループを回さない) |

### まだ判断していない削減候補

以下は候補として挙げたが、この時点では採否を決めていなかった。
**いずれも 2026-07-26 の全面的な作り直しで削除された**（本ファイル冒頭）。

- 設定フラグの固定値化（`layout` の `single`、`enable_ex_notation`、`on_boss_unknown`）
- `/recent` / `/collect` / `/stop` / `/reload` の整理
- `videos.view_count`（取得・保存しているが未使用）

## 2026-07-26: 複数ボスヒットの一本化とバッジ3種の削除

運用者の判断による。判定結果のうち、**投稿先の振り分けにも絞り込みにも使っていなかった列**を削除した。

| 削除したもの | 理由 |
|---|---|
| まとめ動画の別扱い（`is_summary` / `boss_indices`） | 複数ヒットは判定不能に一本化。[判定ロジック](classification.md#複数ボスヒットの扱い) |
| `is_full_auto` / `is_manual` / `is_training_footage` の抽出とバッジ | [判定ロジック](classification.md#フルオート--手動--トレモ) |
| `MetadataResult` データクラス | 残ったのが `damage` 1項目だけになった。`extract_damage()` 関数に置き換え、`classify/metadata.py` は `classify/damage.py` へ改名 |
| Embed の「まとめ動画」専用色（`SUMMARY_COLOR`） | まとめ動画という区分自体が消えた。判定不能と同じ色になる |

### DB スキーマへの影響

削除された列: `videos.boss_indices` / `videos.is_summary` / `videos.is_full_auto` /
`videos.is_manual` / `videos.is_training_footage`

`match_source` は残す。`ex_notation`（番号表記からの推定）であることを Embed に表示し、
確度が低いことを読み手に伝えるために使っている。ただし**判定不能なら `NULL` を保存する**
（1体に絞れていないのに経路だけ残っても意味がないため）。

**既存の `data/bot.db` とは互換性がない。** 前回と同様、移行スクリプトは用意せず
DB ファイルを作り直す前提とした。

### 併せて変更した点

- 複数ヒットした `indices` は **DB からは消えるがログには残す**。判定ロジックの
  チューニングに必要なため（[02 技術構成](../spec/02-architecture.md) §5）

## 2026-07-26: 開始通知を `/start` の返信に統合し、通知フラグを廃止

運用者の判断による。**「開始通知は `/start` のときに流す、ただそれだけ」**という指摘から。

### 何が重複していたか

`/start` 1 回でチャンネルに 3 通流れていた。

| # | 出るもの | 中身 |
|---|---|---|
| 1 | 確認ダイアログ | ボス構成一覧 ＋ 確認ボタン |
| 2 | 確認後の返信 | 「収集を開始しました（対象期間 2026-07）。」 |
| 3 | 開始通知（最大30秒後、ループの最初の巡回） | ボス構成一覧 ＋「収集を開始しました」＋ 開始時刻 |

**ボス構成一覧が 2 回、「収集を開始しました」も 2 回。**3 が持つ固有の情報は開始時刻だけで、
2 に 1 行足せば済んだ。3 を廃止し、開始時刻は 2 に含めた。

| 削除したもの | 理由 |
|---|---|
| ループ初回の開始通知（`_announce_start`） | 上記のとおり `/start` の返信と重複していた |
| `period_state.notified_start` | 守る対象が消えた。再起動時に何も出ないのは従来どおり |
| `period_state.notified_end` | もともと空振りしていた（下記） |
| `mark_notified` / `is_notified` / `claim_notice` | 上記2列を読み書きする仕組みごと |

### `notified_end` が空振りしていた理由

終了通知は `/stop` からしか出ない。`/stop` は収集中でなければコマンド側で弾かれ、
`stop()` は `is_open` を落としてから通知処理に入る。**二重投稿になる経路が存在しなかった。**
「収集中か」の判定は `is_open` だけで足りる。

### DB スキーマへの影響

削除された列: `period_state.notified_start` / `period_state.notified_end`

**既存の `data/bot.db` とは互換性がない。** 同日の他の削減と同じく DB ファイルを作り直す前提。
