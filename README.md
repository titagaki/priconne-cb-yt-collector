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
| `config/config.yaml` | `discord.boss_channels` と `discord.fallback_channel_id`（サンプル値のまま） |
| `config/bosses.yaml` | 今月のボス構成。**毎月書き換える** |

**投稿先チャンネルは Discord 側であらかじめ作成してください。**Bot はチャンネルもスレッドも作りません。
ボスごとの5本と、ボスを特定できなかった動画を流す fallback の計6本を用意し、その ID を
`config.yaml` に書きます。一部のボスを省略した場合、その分は fallback へ流れます。

`bosses.yaml` のエイリアスはボス判定の唯一の正です。実装者・Claude が推測で追加してはいけません。

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
| `/status` | 全員 | 収集中か待機中か、収集開始からの経過、投稿件数 |
| `/start` | 管理者 | 収集開始（ボス構成の確認ボタンつき） |
| `/stop` | 管理者 | 収集停止（データは消さない）とボス別の件数サマリ |

## 動作

1巡でやることは4つだけです。

```
1. ボス名の OR クエリで search.list を1回投げる
2. すでに投稿済みの video_id を除く
3. タイトルに NG ワードを含むものを除く
4. 残りをボスのチャンネルへ「タイトル + URL」の2行で投稿する
```

タイトルから**ボスを1体に特定できたときだけ**そのチャンネルへ、
0体または2体以上ヒットした場合は fallback チャンネルへ投稿します。
通常/持ち越し、ダメージ、フルオートなどは判定しません。

**投稿に成功した動画だけを記録します。**投稿できなかった動画は記録されないので、
次の巡回で再び見つかり自然に再試行されます。

### クォータ

取得経路は Data API v3 の `search.list` 1 本です。結果件数によらず **1 回 100 ユニット固定**
なので、全ボス名を 1 つの OR クエリにまとめて投げます。

```
100ユニット × 48巡/日（30分間隔） = 4,800（1日の上限 10,000）
```

上限の半分以下に収まるため、消費量を記録する仕組みは持ちません。
`search_interval_minutes` を狭める場合は再計算してください（15分なら 9,600 で上限間際）。

## 構成

層は分けていません（詳細は [`docs/spec/02-architecture.md`](docs/spec/02-architecture.md)）。

```
src/priconne_cb_collector/
├── cli.py            起動：設定を読み、Bot を動かす
├── config.py         config.yaml / bosses.yaml の読み込みと検証
├── youtube.py        Data API v3（search.list のみ）
├── classify.py       ボス名マッチと NG ワード判定（純粋関数）
├── store.py          SQLite（投稿済み動画・収集期間の2テーブル）
├── bot.py            常駐ループ、投稿、スラッシュコマンド
└── logging_setup.py  JSON Lines ログ
```

`classify.py` は `httpx` も `discord.py` も `sqlite3` も import しません。
判定を外部サービスなしでテストするためです。

## テスト

```bash
.venv/bin/python -m pytest        # 54件
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

`tests/` は実装と 1:1（`test_config` / `test_classify` / `test_store` / `test_bot`）。
共通のフィクスチャは `tests/conftest.py`、共有定数とテストダブルは `tests/support.py` にあります。

ボス判定は実タイトルを模した表形式のテストケースで検証しています。
