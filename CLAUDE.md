# CLAUDE.md

## Project

- プリコネ（プリンセスコネクト!Re:Dive）クラバト期間中の YouTube 攻略動画を自動収集し、Discord に投稿する Bot
- 仕様は `docs/spec/` が正（`docs/spec/README.md` がインデックス）
- 会話・ドキュメント・コミットメッセージは日本語。コード内の識別子とログは英語

### docs の書き分け

| 置き場所 | 書くもの |
|---|---|
| `docs/spec/` | **Bot が何をするか**だけ。理由もゲーム知識も書かない |
| `docs/discussion/` | **なぜその仕様にしたか。**却下した案、トレードオフ、決定の経緯 |
| `docs/game/` | **プリコネ側の事実。**開催日程、ボス、段階、持ち越し、動画の表記慣習 |
| `docs/reference/` | **加工前の実データ。**判定ロジックを変えたらここで誤爆・取りこぼしを測る |

## Tech Stack

- Python 3.11+ / discord.py 2.x / httpx / SQLite（標準 `sqlite3`、ORM 不要）/ PyYAML
- タイムゾーンは Asia/Tokyo 固定。DB には UTC で保存し、表示時に JST 変換
- ディレクトリ構成は `docs/spec/02-architecture.md` に従う

## Implementation Rules

- **やることは「動画のリストをとってきて投稿する」だけ。**機能を足す前に、それがこの一文に含まれるか確認する。含まれないなら作らない（[削減の記録](docs/discussion/reductions.md)）
- **層を増やさない。**`src/priconne_cb_collector/` はフラットな1ファイル1役。新しいディレクトリを切る前に相談する
- **仕様が未確定の論点は仮実装しない。**先に運用者へ質問し、決定を `docs/discussion/` に理由ごと記録してから `docs/spec/` に反映して実装する
- **`bosses.yaml` のエイリアスを推測で追加しない。**判定の正はこのファイルのみで、編集は運用者が行う
- **取りこぼすくらいなら、関係ない動画が混ざってよい。**判定に迷う実装は投稿する側へ倒す
- YouTube API のクォータを消費する変更（`search.list` の追加・間隔短縮など）は消費量の見積もりを添えて提案する
- 1件の動画の処理失敗が収集ジョブ全体を落とさないようにする（個別 try/except + ログ。**失敗した動画は記録しない**ので次の巡回で再試行される）
- `classify.py` は YouTube / Discord に依存しない純粋関数として書き、表形式のテストケースを添える

## Documentation

- CLAUDE.mdには、毎回必ず守るルールだけを書く(目安100行以内)
- 詳細は上表のとおり `docs/` 配下へ書き分ける。Claudeへの追加指示は `.claude/rules/` に置く
- 未検証の調査結果は `docs/investigations/` に置き、事実と仮説を明記して分ける。検証済みになったら `docs/` へ昇格し、元ファイルは削除する
- 新しい文書を作る前に、`docs/` 配下を検索して重複を確認する
- タスクの進捗状態は `docs/roadmap.md` を更新して管理する
