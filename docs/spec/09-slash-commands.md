# 09. スラッシュコマンド

実装先: `src/priconne_cb_collector/interface/commands.py`

判断の理由は [`docs/discussion/`](../discussion/README.md) を参照。

## 1. コマンド一覧

| コマンド | 権限 | 動作 |
|---|---|---|
| `/status` | 全員 | 収集中か待機中か、収集期間、今期間の収集件数、クォータ残量 |
| `/bosses` | 全員 | 設定中のボス一覧を表示 |
| `/start` | 管理者 | **収集を即時開始する。`mode: trigger` での主たる起動手段。** 実行前に `bosses.yaml` の内容を Embed で提示し、確認ボタンを押させてから開始する |
| `/stop` | 管理者 | 収集を停止し待機状態へ戻す。DB のデータは消さない |
| `/reload` | 管理者 | `bosses.yaml` / `config.yaml` を再読込 |
| `/collect` | 管理者 | 手動で収集を1回実行（クォータ消費の確認ダイアログを出す）。**収集期間外は拒否する** |
| `/period set` | 管理者 | 収集の開始日 / 終了日を手動上書き（manual モードに切替） |
| `/recent [boss]` | 全員 | 直近の収集結果を最大10件表示（未投稿含む） |
| `/suggest_channels` | 管理者 | 収集済み DB を集計し、RSS 未監視でヒット数の多いチャンネルを提案（クォータ消費なし） |

`/collect` を収集期間外で拒否するのは、`videos.cb_period` が NOT NULL だから（[07](07-persistence.md) §1）。

## 2. `/start` の確認ステップ

`/start` は `bosses.yaml` の内容を Embed で提示し、確認ボタンを押させてから開始する。
このステップは省略しない。

## 3. `/suggest_channels` の仕様

- `videos` テーブルを集計し、「ボス判定に成功した動画が多い順」にチャンネルを並べる
- `config.yaml` の `channels` に既に含まれるチャンネルは除外する
- 上位 10 件を「チャンネル名 / ヒット数 / チャンネル ID」の一覧で表示する
- DB 集計のみで実現し、YouTube API は呼ばない（クォータ消費なし）
