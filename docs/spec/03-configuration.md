# 03. 設定ファイル

各値をそう決めた理由は [`docs/discussion/`](../discussion/README.md) を参照。

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
- `month` は待機中 → 収集中の遷移時にも検証される（[04](04-schedule.md) 参照）

## 2. `config/config.yaml`

```yaml
schedule:
  # 収集期間の判定方法。"offset" | "manual" | "trigger"（既定は trigger）
  mode: "trigger"

  # mode: offset の場合 —— 月末日を基準に算出
  start_offset_days: 8      # 末日 - 8日 が収集開始日（トレモ開始に合わせる）
  end_offset_days: 1        # 末日 - 1日 が収集終了日（この日を含む）

  # mode: manual の場合 —— 明示指定（in-game のアナウンスに合わせる用）
  manual_start: null        # "2026-07-23"
  manual_end: null          # "2026-07-30"

  # mode: trigger の場合 —— /start コマンドで収集開始。終了日のみ offset で算出する
  #   （運用者が bosses.yaml を書き換えるタイミングを起点にする）
  # offset 計算上の開始日を過ぎても /start されていない場合に催促を投稿するか
  remind_if_not_started: true

  # 収集開始の何日前に投稿された動画まで検索対象に含めるか
  search_lookback_days: 1

polling:
  # 収集期間中の間隔（期間中は一定。トレモ / 本番で分けない。[04](04-schedule.md) §1）
  rss_interval_minutes: 30
  api_search_interval_hours: 3
  # 収集期間外のチェック間隔（期間に入ったかどうかの確認のみ）
  idle_check_interval_minutes: 60

youtube:
  # RSS 監視対象チャンネル（メインの取得経路）
  channels:
    - id: "UCxxxxxxxxxxxxxxxxxxxxxx"
      name: "サンプルチャンネルA"
    - id: "UCyyyyyyyyyyyyyyyyyyyyyy"
      name: "サンプルチャンネルB"
  # 1日あたりのクォータ上限（既定 10000 のうち何ユニットまで使うか）
  quota_limit_per_day: 9000
  # 除外条件
  exclude:
    min_duration_seconds: 60      # これ未満はショート扱いで除外
    max_duration_seconds: 3600    # 長時間配信アーカイブを除外
    exclude_live: true            # 配信中・配信予定を除外
    title_ng_words: ["ガチャ", "雑談", "実況プレイ"]

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
  # ボス判定できなかった動画をどうするか: "post_as_unknown" | "skip"
  on_boss_unknown: "post_as_unknown"
```

`channels` はサンプル値。**運用者が実際のチャンネル ID を設定する必要がある。**

## 3. 環境変数（`.env`）

```
DISCORD_BOT_TOKEN=
YOUTUBE_API_KEY=
LOG_LEVEL=INFO
```

**シークレットは YAML に書かない。** `.env.example` を用意すること。
