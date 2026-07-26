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
| 02 | [技術構成](02-architecture.md) | ライブラリ、ファイル構成、DB スキーマ、ログ、テスト |
| 03 | [収集期間とコマンド](03-schedule.md) | `/start` 〜 `/stop` の2状態、スラッシュコマンド |
| 04 | [取得と投稿](04-collection.md) | API 検索、投稿先の決定、NG ワード、投稿制御 |
| 05 | [設定ファイル](05-configuration.md) | `bosses.yaml` / `config.yaml` / `.env` |

## 実装者への注意

- **やることは「動画のリストをとってきて投稿する」だけ。**機能を足す前に、それが
  この一文に含まれるか確認する（[削減の記録](../discussion/reductions.md)）
- 仕様が未確定の論点は**仮実装せず、運用者に質問して決める。** 決定は [`docs/discussion/`](../discussion/README.md) に理由ごと記録してから、この配下へ反映する
- ボス判定の唯一の正は `config/bosses.yaml` の内容。実装者がエイリアスを推測で追加しない
- **取りこぼすくらいなら、関係ない動画が混ざってよい。**判断に迷ったら投稿する側へ倒す
