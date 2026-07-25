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

## 2. レイヤ構成

依存は **上から下への一方向のみ**。下位層は上位層を import しない。

| 層 | 責務 | 依存してよいもの |
|---|---|---|
| `interface/` | Discord 配信層。スラッシュコマンド、Embed、投稿キュー、Bot 本体 | services / adapters / domain |
| `services/` | ユースケース。収集パイプライン、期間ライフサイクル | adapters / domain |
| `adapters/` | 外部 I/O。SQLite、YouTube RSS / Data API、設定ファイル | domain |
| `domain/` | **依存なし。** dataclass と純粋関数（判定ロジック、期間計算） | 標準ライブラリのみ |

`domain/` は `httpx` / `discord.py` / `sqlite3` のいずれも import しない。
これによりボス判定・期間判定を外部サービスなしでテストできる（[12](12-implementation-order.md) 参照）。

## 3. ディレクトリ構成

src レイアウトの単一パッケージ。`pip install -e .` で `priconne-cb-collector` コマンドが入る。

```
priconne-cb-yt-collector/
├── pyproject.toml           # PEP 621。依存・entry point・ruff / pytest 設定
├── config/
│   ├── config.yaml          # 運用設定（Git管理する）
│   └── bosses.yaml          # 今月のボス構成（毎月書き換える）
├── src/priconne_cb_collector/
│   ├── __main__.py          # python -m priconne_cb_collector
│   ├── cli.py               # エントリポイント。設定読込と依存の組み立て
│   ├── logging_setup.py     # JSON Lines ログ
│   ├── domain/
│   │   ├── models.py        # Boss / Period / VideoMeta / Classification 等
│   │   ├── settings.py      # 設定スキーマ（dataclass のみ）
│   │   ├── schedule.py      # 稼働期間・フェーズ判定（純粋関数）
│   │   └── classify/
│   │       ├── normalize.py    # 正規化
│   │       ├── boss.py         # ボス判定
│   │       ├── battle_type.py  # 通常/持ち越し判定
│   │       └── metadata.py     # 段階・ダメージ・フルオート等の抽出
│   ├── adapters/
│   │   ├── config_file.py   # YAML 読み込み・バリデーション
│   │   ├── sqlite_store.py  # SQLite 永続化
│   │   ├── youtube_rss.py   # チャンネル RSS 取得
│   │   └── youtube_api.py   # Data API v3 クライアント（クォータ管理込み）
│   ├── services/
│   │   ├── collection.py    # 収集パイプライン（取得→判定→除外→保存）
│   │   └── lifecycle.py     # 期間の解決・遷移・通知フラグ
│   └── interface/
│       ├── bot.py           # discord.Client、ポーリングループ、遷移通知
│       ├── commands.py      # スラッシュコマンド
│       ├── embeds.py        # Embed 生成
│       └── poster.py        # 投稿キュー・スレッド管理
├── tests/
├── data/bot.db
├── .env.example
└── README.md
```

## 4. モジュールと仕様章の対応

| モジュール | 対応する仕様 |
|---|---|
| `adapters/config_file.py` | [03. 設定ファイル](03-configuration.md) |
| `domain/schedule.py`, `services/lifecycle.py` | [04. 稼働期間・フェーズ判定](04-schedule.md) |
| `adapters/youtube_rss.py`, `adapters/youtube_api.py`, `services/collection.py` | [05. 動画の取得](05-collection.md) |
| `domain/classify/` | [06. 判定ロジック](06-classification.md) |
| `adapters/sqlite_store.py` | [07. 永続化](07-persistence.md) |
| `interface/poster.py`, `interface/embeds.py` | [08. Discord 投稿](08-discord-posting.md) |
| `interface/commands.py` | [09. スラッシュコマンド](09-slash-commands.md) |
