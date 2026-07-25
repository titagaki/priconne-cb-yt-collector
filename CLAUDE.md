# CLAUDE.md

## Project

- プリコネ（プリンセスコネクト!Re:Dive）クラバト期間中の YouTube 攻略動画を自動収集し、Discord に投稿する Bot
- 仕様は `docs/spec/` が正（`docs/spec/README.md` がインデックス）
- 会話・ドキュメント・コミットメッセージは日本語。コード内の識別子とログは英語

## Tech Stack

- Python 3.11+ / discord.py 2.x / httpx / feedparser / SQLite（標準 `sqlite3`、ORM 不要）/ PyYAML
- タイムゾーンは Asia/Tokyo 固定。DB には UTC で保存し、表示時に JST 変換
- ディレクトリ構成は `docs/spec/02-architecture.md` に従う

## Implementation Rules

- **`docs/spec/11-open-questions.md` の未確定事項は仮実装しない。**先に運用者へ質問し、決定を仕様に反映してから実装する
- **`bosses.yaml` のエイリアスを推測で追加しない。**判定の正はこのファイルのみで、編集は運用者が行う
- 誤爆（無関係な動画の投稿）より取りこぼしを許容する。判定に迷う実装は投稿しない側へ倒す
- YouTube API のクォータを消費する変更（`search.list` の追加・間隔短縮など）は消費量の見積もりを添えて提案する
- 1件の動画の処理失敗が収集ジョブ全体を落とさないようにする（個別 try/except + `status="error"` 記録）
- 判定ロジック（`classify/`）は YouTube / Discord に依存しない純粋関数として書き、表形式のテストケースを添える
- 実装順序は `docs/spec/12-implementation-order.md` に従う（classify を先に固める）

## Documentation

- CLAUDE.mdには、毎回必ず守るルールだけを書く(目安100行以内)
- 詳細な仕様、設計理由は `docs/` に、Claudeへの追加指示は `.claude/rules/` に置く
- 未検証の調査結果は `docs/investigations/` に置き、事実と仮説を明記して分ける。検証済みになったら `docs/` へ昇格し、元ファイルは削除する
- 新しい文書を作る前に、`docs/` 配下を検索して重複を確認する
- タスクの進捗状態は `docs/roadmap.md` を更新して管理する
