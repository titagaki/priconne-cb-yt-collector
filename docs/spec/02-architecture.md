# 02. 技術構成

## 1. 技術スタック

| 項目 | 指定 |
|---|---|
| 言語 | Python 3.11+ |
| Discord | discord.py 2.x（スラッシュコマンド対応） |
| スケジューラ | `discord.ext.tasks` |
| HTTP | httpx（非同期） |
| RSS | feedparser |
| DB | SQLite（標準ライブラリ `sqlite3`。ORM 不要） |
| 設定 | YAML（PyYAML） |
| タイムゾーン | **Asia/Tokyo 固定**。DB には UTC で保存し、表示時に JST 変換 |

## 2. ディレクトリ構成

```
priconne-cb-bot/
├── config/
│   ├── config.yaml          # 運用設定（Git管理する）
│   └── bosses.yaml          # 今月のボス構成（毎月書き換える）
├── src/
│   ├── main.py              # エントリポイント、Bot 起動
│   ├── config.py            # 設定読み込み・バリデーション
│   ├── schedule.py          # 稼働期間・フェーズ判定
│   ├── sources/
│   │   ├── rss.py           # チャンネル RSS 取得
│   │   └── youtube_api.py   # Data API v3 クライアント（クォータ管理込み）
│   ├── classify/
│   │   ├── boss.py          # ボス判定
│   │   ├── battle_type.py   # 通常/持ち越し判定
│   │   └── metadata.py      # 段階・ダメージ・フルオート等の抽出
│   ├── store.py             # SQLite 永続化
│   ├── discord_bot/
│   │   ├── poster.py        # Embed 生成・投稿キュー
│   │   └── commands.py      # スラッシュコマンド
│   └── models.py            # dataclass 定義
├── tests/
├── data/
│   └── bot.db
├── .env.example
└── README.md
```

## 3. モジュールと仕様章の対応

| モジュール | 対応する仕様 |
|---|---|
| `config.py` | [03. 設定ファイル](03-configuration.md) |
| `schedule.py` | [04. 稼働期間・フェーズ判定](04-schedule.md) |
| `sources/` | [05. 動画の取得](05-collection.md) |
| `classify/` | [06. 判定ロジック](06-classification.md) |
| `store.py` | [07. 永続化](07-persistence.md) |
| `discord_bot/poster.py` | [08. Discord 投稿](08-discord-posting.md) |
| `discord_bot/commands.py` | [09. スラッシュコマンド](09-slash-commands.md) |

`classify/` は YouTube にも Discord にも依存しない純粋関数群として実装する（テスト容易性のため。[12](12-implementation-order.md) 参照）。
