# 仕様書インデックス

プリコネ クラバト攻略動画 Discord Bot の仕様。**この配下が正**とする。

## 読む順序

| # | 文書 | 内容 |
|---|---|---|
| 01 | [概要・スコープ・用語](01-overview.md) | 目的、基本方針、やること/やらないこと、用語定義 |
| 02 | [技術構成](02-architecture.md) | 言語・ライブラリ選定、ディレクトリ構成 |
| 03 | [設定ファイル](03-configuration.md) | `bosses.yaml` / `config.yaml` / `.env` |
| 04 | [稼働期間・フェーズ判定](04-schedule.md) | idle / training / battle の3フェーズとその遷移 |
| 05 | [動画の取得](05-collection.md) | チャンネル RSS、Data API v3 検索、クォータ管理 |
| 06 | [判定ロジック](06-classification.md) | 正規化、ボス判定、通常/持ち越し判定、除外フィルタ |
| 07 | [永続化](07-persistence.md) | SQLite スキーマ、重複排除 |
| 08 | [Discord 投稿](08-discord-posting.md) | レイアウト、Embed 形式、投稿制御 |
| 09 | [スラッシュコマンド](09-slash-commands.md) | コマンド一覧と権限 |
| 10 | [非機能要件](10-non-functional.md) | エラーハンドリング、ログ、テスト |
| 11 | [未確定事項](11-open-questions.md) | **実装前に必ず確認すること** |
| 12 | [実装順序](12-implementation-order.md) | 推奨する着手順 |

## 実装者への注意

- **未確定事項（[11](11-open-questions.md)）は仮実装せず、運用者に質問すること。**
- 判定ロジックの唯一の正は `config/bosses.yaml` の内容。実装者がエイリアスを推測で追加しない。
- 誤爆（無関係な動画の投稿）より取りこぼしを許容する方針。判断に迷ったら投稿しない側へ倒す。
