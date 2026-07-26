# 仕様書インデックス

プリコネ クラバト攻略動画 Discord Bot の仕様。**この配下が正**とする。

ここには **Bot が何をするか**だけを書く。

- なぜその仕様にしたか → [`docs/discussion/`](../discussion/README.md)
- プリコネ（ゲーム）側の事実 → [`docs/game/`](../game/README.md)
- 判定の検証に使う実データ → [`docs/reference/`](../reference/README.md)

## 読む順序

| # | 文書 | 内容 |
|---|---|---|
| 01 | [概要・スコープ・用語](01-overview.md) | 目的、基本方針、やること/やらないこと、用語定義 |
| 02 | [技術構成](02-architecture.md) | 言語・ライブラリ選定、ディレクトリ構成 |
| 03 | [設定ファイル](03-configuration.md) | `bosses.yaml` / `config.yaml` / `.env` |
| 04 | [収集期間](04-schedule.md) | 収集する / しないの2状態とその遷移 |
| 05 | [動画の取得](05-collection.md) | Data API v3 検索、videos.list による補完、クォータ管理 |
| 06 | [判定ロジック](06-classification.md) | 正規化、ボス判定、通常/持ち越し判定、除外フィルタ |
| 07 | [永続化](07-persistence.md) | SQLite スキーマ、重複排除 |
| 08 | [Discord 投稿](08-discord-posting.md) | レイアウト、Embed 形式、投稿制御 |
| 09 | [スラッシュコマンド](09-slash-commands.md) | コマンド一覧と権限 |
| 10 | [非機能要件](10-non-functional.md) | エラーハンドリング、ログ、テスト |
| 12 | [実装順序](12-implementation-order.md) | 推奨する着手順 |

## 実装者への注意

- 仕様が未確定の論点は**仮実装せず、運用者に質問して決める。** 決定は [`docs/discussion/`](../discussion/README.md) に理由ごと記録してから、この配下へ反映する。
- 判定ロジックの唯一の正は `config/bosses.yaml` の内容。実装者がエイリアスを推測で追加しない。
- **取りこぼすくらいなら、関係ない動画が混ざってよい。**判断に迷ったら投稿する側へ倒す。
