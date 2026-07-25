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
| `.env` | `DISCORD_BOT_TOKEN` / `YOUTUBE_API_KEY` |
| `config/config.yaml` | `discord.channel_id`、`youtube.channels`（サンプル値のまま） |
| `config/bosses.yaml` | 今月のボス構成。**毎月書き換える** |

`bosses.yaml` のエイリアスは判定ロジックの唯一の正です。実装者・Claude が推測で追加してはいけません。

## 起動

```bash
.venv/bin/python src/main.py
```

既定は `trigger` モードです。日付では自動起動せず、Discord で `/start` を実行した時点から収集が始まります。
これは「`bosses.yaml` を今月の構成に書き換える」作業と起動を1操作にまとめ、前月のボス名で収集し続ける事故を防ぐためです。
offset 計算上のトレモ開始日を過ぎても `/start` されていない場合は、Discord へ催促を1回だけ投稿します。

## スラッシュコマンド

| コマンド | 権限 | 動作 |
|---|---|---|
| `/status` | 全員 | フェーズ、次の遷移、収集件数、クォータ残量 |
| `/bosses` | 全員 | 設定中のボス一覧 |
| `/recent [boss]` | 全員 | 直近の収集結果を最大10件 |
| `/start` | 管理者 | 稼働開始（ボス構成の確認ボタンつき） |
| `/stop` | 管理者 | 稼働停止（データは消さない） |
| `/reload` | 管理者 | `config.yaml` / `bosses.yaml` の再読込 |
| `/collect [api_search]` | 管理者 | 手動収集（クォータ消費の確認つき） |
| `/period set` | 管理者 | 期間を手動上書き（manual モードへ切替） |
| `/suggest_channels` | 管理者 | RSS 監視候補の提案（クォータ消費なし） |

## クォータ

`search.list` は 1 回 100 ユニット、`videos.list` は 50 件まとめて 1 ユニットです。
ボス5体の検索 1 巡で 500 ユニット消費するため、既定の 3 時間間隔（1日8巡 = 4,000ユニット）が上限の目安です。
`quota_limit_per_day` を超えそうな場合と `quotaExceeded` を受けた場合は、**停止せず RSS のみに縮退**します。

## テスト

```bash
.venv/bin/python -m pytest
```

判定ロジック（`src/classify/`）は YouTube にも Discord にも依存しない純粋関数で、実タイトルを模した表形式のテストケースで検証しています。
