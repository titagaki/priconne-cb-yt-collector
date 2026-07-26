# priconne-cb-yt-collector

プリンセスコネクト!Re:Dive のクランバトル期間中、YouTube に投稿されるボス攻略動画を自動収集し、Discord へ投稿する Bot。

仕様の正は [`docs/spec/`](docs/spec/README.md)（[インデックス](docs/spec/README.md)）。進捗は [`docs/roadmap.md`](docs/roadmap.md)。

## セットアップ

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env      # DISCORD_BOT_TOKEN / YOUTUBE_API_KEY を記入
```

運用開始前に、以下は**運用者が手で設定する**必要があります。

| ファイル | 項目 |
|---|---|
| `.env` | `DISCORD_BOT_TOKEN` / `YOUTUBE_API_KEY`（`LOG_LEVEL` は任意、既定 INFO） |
| `config/config.yaml` | `discord.channel_id`、`youtube.channels`（サンプル値のまま） |
| `config/bosses.yaml` | 今月のボス構成。**毎月書き換える** |

`bosses.yaml` のエイリアスは判定ロジックの唯一の正です。実装者・Claude が推測で追加してはいけません。

## 起動

```bash
.venv/bin/priconne-cb-collector            # または python -m priconne_cb_collector
.venv/bin/priconne-cb-collector --check    # 設定の検証のみ。Discord へ接続しない
```

`--config-dir` / `--db` / `--log-dir` で配置を変更できます（環境変数 `PRICONNE_CONFIG_DIR` / `PRICONNE_DB_PATH` / `PRICONNE_LOG_DIR` でも可）。

日付の設定はありません。Discord で `/start` を実行した時点から収集が始まり、`/stop` するまで続きます。
これは「`bosses.yaml` を今月の構成に書き換える」作業と起動を1操作にまとめ、前月のボス名で収集し続ける事故を防ぐためです。
**自動では終わらないので、クラバトが終わったら `/stop` してください。**

## スラッシュコマンド

| コマンド | 権限 | 動作 |
|---|---|---|
| `/status` | 全員 | 収集中か待機中か、収集開始からの経過、収集件数、クォータ残量 |
| `/recent [boss]` | 全員 | 直近の収集結果を最大10件 |
| `/start` | 管理者 | 収集開始（ボス構成の確認ボタンつき） |
| `/stop` | 管理者 | 収集停止（データは消さない） |
| `/reload` | 管理者 | `config.yaml` / `bosses.yaml` の再読込 |
| `/collect [api_search]` | 管理者 | 手動収集（クォータ消費の確認つき） |
| `/suggest_channels` | 管理者 | RSS 監視候補の提案（クォータ消費なし） |

## クォータ

`search.list` は 1 回 100 ユニット、`videos.list` は 50 件まとめて 1 ユニットです。
ボス5体の検索 1 巡で 500 ユニット消費するため、既定の 3 時間間隔（1日8巡 = 4,000ユニット）が上限の目安です。
`quota_limit_per_day` を超えそうな場合と `quotaExceeded` を受けた場合は、**停止せず RSS のみに縮退**します。

## 構成

依存は上から下への一方向のみです（詳細は [`docs/spec/02-architecture.md`](docs/spec/02-architecture.md)）。

```
src/priconne_cb_collector/
├── interface/   Discord 配信層（コマンド、Embed、投稿キュー、Bot 本体）
├── services/    ユースケース（収集パイプライン、期間ライフサイクル）
├── adapters/    外部 I/O（SQLite、YouTube RSS / Data API、設定ファイル）
└── domain/      依存なし。dataclass と純粋関数（判定ロジック、期間計算）
```

`domain/` は `httpx` も `discord.py` も `sqlite3` も import しません。判定ロジックを外部サービスなしでテストするためです。

## テスト

```bash
.venv/bin/python -m pytest              # 268件
.venv/bin/python -m pytest tests/domain # 層ごとに実行できる
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

`tests/` は実装と同じ層構造です（`tests/domain/`, `tests/adapters/`, `tests/services/`, `tests/interface/`）。
共通のフィクスチャは `tests/conftest.py`、共有定数とテストダブルは `tests/support.py` にあります。

判定ロジック（`domain/classify/`）は実タイトルを模した表形式のテストケースで検証しています。
レイヤの依存方向は `tests/test_layering.py` が AST 解析で機械的に検証しています。
