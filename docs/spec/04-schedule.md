# 04. 稼働期間・フェーズ判定

実装先: `src/priconne_cb_collector/domain/schedule.py`（期間計算の純粋関数）、
`src/priconne_cb_collector/services/lifecycle.py`（期間の解決・遷移・通知フラグ）

## 1. 3つのフェーズ

Bot は常に以下いずれかのフェーズにある。**収集対象期間はトレーニングモード開始時点から始まる。**

| フェーズ | 期間 | 挙動 |
|---|---|---|
| `idle` | それ以外 | YouTube へ一切通信しない。期間判定のみ |
| `training` | トレモ開始 〜 クラバト開始前日 | 収集する。ポーリング間隔は広め |
| `battle` | クラバト開始 〜 終了日 | 収集する。ポーリング間隔は短め |

トレーニングモード期間中に今月のボスが判明するため、**この時点から検証動画が出始める。ここを取り逃すと初日の情報収集に間に合わない**というのが早期起動の理由。

## 2. 期間算出ロジック

```
mode == "offset"  → その月の末日 D に対して
                    battle_start   = D - start_offset_days           の 00:00 JST
                    battle_end     = D - end_offset_days             の 23:59:59 JST
                    training_start = battle_start - training_days_before の 00:00 JST

mode == "manual"  → manual_training_start / manual_battle_start / manual_end をそのまま使う
                    manual_training_start が null の場合は manual_battle_start と同値とみなす

mode == "trigger" → training_start = /start コマンドが実行された時刻
                    battle_start / battle_end は offset と同じ式で算出
                    （運用者が bosses.yaml を書き換えたタイミングを起点にする運用）
```

既定値（`start_offset_days: 5` / `end_offset_days: 1` / `training_days_before: 3`）での例:

| 末日 | トレモ開始 | クラバト | 稼働期間 |
|---|---|---|---|
| 31日 | 23日 | 26日〜30日 | 23日〜30日（8日間） |
| 30日 | 22日 | 25日〜29日 | 22日〜29日 |
| 28日 | 20日 | 23日〜27日 | 20日〜27日 |

**実際の開催日程は月ごとに前後する。** ズレる月は `manual` または `trigger` モードで運用する（[11-1](11-open-questions.md#11-1-稼働期間のオフセット値) 参照）。

## 3. フェーズごとの挙動と遷移

- **`idle` 中:** `idle_check_interval_minutes` 間隔で期間判定のみ実行。YouTube への通信は一切しない
- **`idle` → `training` 遷移時:**
  - **`bosses.yaml` の `month` が当月と一致するか検証する。不一致なら収集を開始せず、Discord に「ボス構成が未更新」の警告を投稿して `idle` に留まる**（前月のボス名で検索し続ける事故を防ぐ）
  - 一致していれば開始通知（ボス構成一覧つき）を投稿し、初回収集を実行
  - `layout: per_boss_thread` の場合、このタイミングでボス別スレッドを作成する（[08](08-discord-posting.md)）
- **`training` → `battle` 遷移時:** 本番開始通知を投稿し、ポーリング間隔を短い方へ切り替える
- **`battle` 終了時:** 終了通知（ボス別の収集件数サマリ）を投稿し、ポーリング停止
- **再起動時:** 現在時刻からフェーズを再計算して即座に再開する。フェーズ遷移通知は重複投稿しない（遷移済みフラグを DB の `period_state` に持つ。[07](07-persistence.md)）
- **`mode: trigger` の場合:** `/start` されるまでは `idle` のまま。日付では自動開始しない
- **`/start` 催促（11-1 で決定）:** `mode: trigger` かつ `remind_if_not_started: true` の場合、offset 式で算出したトレモ開始日時を過ぎても `/start` されていなければ、idle チェック時に Discord へ催促を投稿する。**1期間につき1回のみ**（`period_state.notified_reminder` で管理。[07](07-persistence.md)）
