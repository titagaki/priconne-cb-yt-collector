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

**収集期間の設定は無い。**開始と終了は `/start` / `/stop` のみで決まる（[04](04-schedule.md) §2）。

```yaml
polling:
  # 収集中の間隔（収集中は一定。トレモ / 本番で分けない。[04](04-schedule.md) §1）
  rss_interval_minutes: 30
  api_search_interval_hours: 3
  # 待機中はループ自体を回さないため、idle 用の間隔設定は無い

youtube:
  # RSS 監視対象チャンネル（メインの取得経路）
  channels:
    - id: "UCxxxxxxxxxxxxxxxxxxxxxx"
      name: "サンプルチャンネルA"
    - id: "UCyyyyyyyyyyyyyyyyyyyyyy"
      name: "サンプルチャンネルB"
  # 1日あたりのクォータ上限（既定 10000 のうち何ユニットまで使うか）
  quota_limit_per_day: 9000
  # /start の何日前に投稿された動画まで API 検索の対象に含めるか
  search_lookback_days: 1
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
