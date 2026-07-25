# 04. 収集期間の判定

実装先: `src/priconne_cb_collector/domain/schedule.py`（期間計算の純粋関数）、
`src/priconne_cb_collector/services/lifecycle.py`（期間の解決・遷移・通知フラグ）

判断の理由は [discussion/収集期間](../discussion/schedule.md)、
ゲーム側の日程は [game/クランバトル](../game/clan-battle.md#開催スケジュール) を参照。

## 1. 状態

Bot の状態は2値のみ。トレーニング期間と本番期間は区別しない。

| 状態 | 期間 | 挙動 |
|---|---|---|
| 収集中 | 収集開始 〜 収集終了 | RSS / API 検索を回して投稿する |
| 待機中 | それ以外 | YouTube へ一切通信しない。期間に入ったかの判定のみ |

## 2. 期間算出ロジック

```
mode == "offset"  → その月の末日 D に対して
                    start = D - start_offset_days の 00:00 JST
                    end   = D - end_offset_days   の 23:59:59 JST

mode == "manual"  → manual_start / manual_end をそのまま使う
                    どちらか一方でも未設定なら期間なし（待機中のまま）

mode == "trigger" → start = /start コマンドが実行された時刻
                    end は offset と同じ式で算出
```

既定値（`start_offset_days: 8` / `end_offset_days: 1`）での結果:

| 末日 | 収集期間 |
|---|---|
| 31日 | 23日〜30日（8日間） |
| 30日 | 22日〜29日 |
| 29日 | 21日〜28日 |
| 28日 | 20日〜27日 |

`offset` モードでは、現在時刻がその月の期間終了を過ぎている場合、翌月の期間を返す。

## 3. 挙動と遷移

- **待機中:** ポーリングループの間隔を `idle_check_interval_minutes` へ落とし、期間判定のみ実行する。
  YouTube への通信は一切しない。収集中に入ると 1 分間隔へ戻す
  - `/start`・`/period set` はループを即時再起動する
- **待機中 → 収集中の遷移時:**
  - `bosses.yaml` の `month` が当月と一致するか検証する。**不一致なら収集を開始せず、Discord に「ボス構成が未更新」の警告を投稿して待機したままにする**
  - 一致していれば開始通知（ボス構成一覧つき）を投稿し、初回収集を実行
  - `layout: per_boss_thread` の場合、このタイミングでボス別スレッドを作成する（[08](08-discord-posting.md)）
- **収集中 → 待機中の遷移時:** 未投稿分を投げ切ってから終了通知（ボス別の収集件数サマリ）を投稿し、ポーリング停止
- **再起動時:** 現在時刻から状態を再計算して即座に再開する。遷移通知は重複投稿しない（遷移済みフラグは `period_state`。[07](07-persistence.md)）
- **`mode: trigger` の場合:** `/start` されるまでは待機中のまま。日付では自動開始しない
- **`/start` 催促:** `mode: trigger` かつ `remind_if_not_started: true` の場合、offset 式で算出した開始日時を過ぎても `/start` されていなければ、待機中のチェック時に Discord へ催促を投稿する。**1期間につき1回のみ**（`period_state.notified_reminder`）
