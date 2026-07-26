# 05. 設定ファイル

実装先: `src/priconne_cb_collector/config.py`

各値をそう決めた理由は [`docs/discussion/`](../discussion/README.md) を参照。

## 1. `config/bosses.yaml`

運用者が毎月書き換えるファイル。**このファイルの内容がボス判定の唯一の正になる。**

```yaml
# 対象月（YYYY-MM）。cb_period と一致しない間は収集しない（[03](03-schedule.md) §3）
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
- `name` は検索クエリと判定の両方に使う。`aliases` は判定にのみ使う（[04](04-collection.md)）
- `aliases` は省略可（省略時は `name` のみを使う）
- `aliases` に短すぎる文字列（2文字以下）が含まれる場合は起動時に警告を出す。誤マッチの原因になるため
- **エイリアスは実装者が推測で追加しないこと。** 上記の値はサンプルであり、運用者が編集する

## 2. `config/config.yaml`

**収集期間の設定は無い。**開始と終了は `/start` / `/stop` のみで決まる（[03](03-schedule.md) §2）。

```yaml
polling:
  # API 検索の間隔（収集中は一定）
  #   1巡 = 1クエリ = 100ユニット。30分間隔なら 48巡/日 = 4,800ユニット（上限 10,000）
  search_interval_minutes: 30

youtube:
  # /start の何日前に投稿された動画まで検索対象に含めるか
  search_lookback_days: 1
  # タイトルにこれらを含む動画は投稿しない
  title_ng_words: ["ガチャ", "雑談", "実況プレイ"]

discord:
  # 投稿先チャンネル。**あらかじめ Discord 側で作成しておくこと**（Bot は作らない）
  boss_channels:
    1: 000000000000000000
    2: 000000000000000000
    3: 000000000000000000
    4: 000000000000000000
    5: 000000000000000000
  # ボスを1体に特定できなかった動画の投稿先（複数ボス名を含む動画もここ）
  fallback_channel_id: 000000000000000000
  post_interval_seconds: 2
```

### 要件

- **`fallback_channel_id` は必須。**未設定なら起動失敗させる（投稿先が無いと動画を捨てることになるため）
- `boss_channels` に無いボスは `fallback_channel_id` へ投稿する。**起動は止めず、警告のみ**
- **監視チャンネルの設定は無い。**検索クエリは `bosses.yaml` から組み立てる（[04](04-collection.md) §1）

## 3. 環境変数（`.env`）

```
DISCORD_BOT_TOKEN=
YOUTUBE_API_KEY=
LOG_LEVEL=INFO
```

**シークレットは YAML に書かない。** `.env.example` を用意すること。

`DISCORD_BOT_TOKEN` と `YOUTUBE_API_KEY` はどちらも必須。未設定なら起動を中止する
（API 検索が唯一の取得経路なので、キーが無いと何も収集できない）。
