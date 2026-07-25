# 03. 設定ファイル

## 1. `config/bosses.yaml`

運用者が毎月書き換えるファイル。**このファイルの内容が判定ロジックの唯一の正になる。**

```yaml
# 対象月（YYYY-MM）。この値と実行時の月が一致しない場合は起動時に警告する
month: "2026-07"

bosses:
  - index: 1
    name: "ワイバーン"
    aliases: ["ワイバーン", "ワイバン", "wyvern"]
  - index: 2
    name: "デミカリド"
    aliases: ["デミカリド", "デミカリ"]
  - index: 3
    name: "ライデン"
    aliases: ["ライデン", "雷電"]
  - index: 4
    name: "スピリットホーン"
    aliases: ["スピリットホーン", "スピホン"]
  - index: 5
    name: "オルレオン"
    aliases: ["オルレオン", "オルレ"]
```

### 要件

- `index` は 1〜5、重複不可、5件必須。違反時は**起動失敗**させる
- `aliases` は省略可（省略時は `name` のみを使う）
- `aliases` に短すぎる文字列（2文字以下）が含まれる場合は起動時に警告を出す。誤マッチの原因になるため
- ファイルはホットリロード可能にする（`/reload` コマンドで再読込。Bot 再起動を不要にする）
- **エイリアスは実装者が推測で追加しないこと。** 上記の値はサンプルであり、運用者が編集する
- `month` は idle → training 遷移時にも検証される（[04](04-schedule.md) 参照）

## 2. `config/config.yaml`

```yaml
schedule:
  # 稼働期間の判定方法。"offset" | "manual" | "trigger"
  mode: "offset"

  # mode: offset の場合 —— 月末日を基準に算出
  start_offset_days: 5      # 末日 - 5日 が クラバト開始日
  end_offset_days: 1        # 末日 - 1日 が クラバト終了日（この日を含む）
  training_days_before: 3   # クラバト開始の何日前からトレーニングモードが始まるか

  # mode: manual の場合 —— 明示指定（in-game のアナウンスに合わせる用）
  manual_training_start: null   # "2026-07-23"
  manual_battle_start: null     # "2026-07-26"
  manual_end: null              # "2026-07-30"

  # mode: trigger の場合 —— /start コマンドで稼働開始。終了日のみ offset で算出する
  #   （運用者が bosses.yaml を書き換えるタイミングを起点にする）

  # 稼働開始の何日前に投稿された動画まで検索対象に含めるか
  search_lookback_days: 1

polling:
  # トレーニング期間中の間隔（動画本数が少ないため広め）
  training_rss_interval_minutes: 20
  training_api_search_interval_hours: 6
  # クラバト本番期間中の間隔
  rss_interval_minutes: 10
  api_search_interval_hours: 3
  # 稼働期間外のチェック間隔（期間に入ったかどうかの確認のみ）
  idle_check_interval_minutes: 60

youtube:
  # RSS 監視対象チャンネル（メインの取得経路）
  channels:
    - id: "UCxxxxxxxxxxxxxxxxxxxxxx"
      name: "サンプルチャンネルA"
    - id: "UCyyyyyyyyyyyyyyyyyyyyyy"
      name: "サンプルチャンネルB"
  # API 検索のベースクエリ。ボス名がこれに連結される
  search_query_base: "プリコネ クラバト"
  # 1日あたりのクォータ上限（既定 10000 のうち何ユニットまで使うか）
  quota_limit_per_day: 9000
  # 除外条件
  exclude:
    min_duration_seconds: 60      # これ未満はショート扱いで除外
    max_duration_seconds: 3600    # 長時間配信アーカイブを除外
    exclude_live: true            # 配信中・配信予定を除外
    title_ng_words: ["ガチャ", "雑談", "実況プレイ", "初心者"]

discord:
  # "single" = 1チャンネルに全部 / "per_boss_thread" = ボスごとのスレッド
  layout: "per_boss_thread"
  channel_id: 000000000000000000
  # 1ボスあたり1日に投稿する最大件数（0 = 無制限）
  max_posts_per_boss_per_day: 15
  post_interval_seconds: 2

classify:
  # ボス名でマッチしなかった動画に EX表記判定を適用するか
  enable_ex_notation: true
  # ボス判定できなかった動画をどうするか: "skip" | "post_as_unknown"
  on_boss_unknown: "skip"
```

`channels` はサンプル値。運用者が実際のチャンネル ID を設定する必要がある（[11-5](11-open-questions.md#11-5-rss-監視チャンネルの初期リスト) 参照）。

## 3. 環境変数（`.env`）

```
DISCORD_BOT_TOKEN=
YOUTUBE_API_KEY=
LOG_LEVEL=INFO
```

**シークレットは YAML に書かない。** `.env.example` を用意すること。
