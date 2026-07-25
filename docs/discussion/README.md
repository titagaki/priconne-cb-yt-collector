# 設計判断の記録

**なぜその仕様にしたか**を残す。仕様そのものは [`docs/spec/`](../spec/README.md) が正。

spec 側には「何をするか」だけを書き、理由・却下した案・トレードオフはここに置く。
仕様を変更するときは、まずここに理由を書いてから spec を直す。

| 文書 | 扱う範囲 |
|---|---|
| [スコープと方針](scope.md) | 何をやらないか、取りこぼしと誤爆のどちらを許容するか |
| [収集期間](schedule.md) | 状態を2値にした理由、trigger を既定にした理由、催促の要否 |
| [動画の取得](collection.md) | RSS と API 検索の併用、クォータ配分、videos.list の扱い |
| [判定ロジック](classification.md) | EX表記の採否、正規表現の落とし穴、扱わないと決めた項目 |
| [Discord 投稿](posting.md) | レイアウト、Embed に載せる情報、投稿制御 |
| [削減の記録](reductions.md) | 実装後に削除した機能とその理由 |

## 決定済みの論点

実装前に運用者へ確認し、決定した項目（いずれも 2026-07-25 決定）。

| # | 論点 | 決定 | 詳細 |
|---|---|---|---|
| 1 | 収集開始の既定モード | `trigger` + 催促あり | [schedule.md](schedule.md#既定モードを-trigger-にした理由) |
| 2 | EX表記を採用するか | 折衷案で採用（分類のみ） | [classification.md](classification.md#ex表記の採否) |
| 3 | 品質フィルタの要否 | フィルタなし（速報性優先） | [collection.md](collection.md#品質フィルタを入れない理由) |
| 4 | 期間終了後の未投稿分 | 投げ切る | [posting.md](posting.md#期間終了時にキューを投げ切る理由) |
| 5 | RSS 監視チャンネルの初期リスト | `/suggest_channels` を実装 | [collection.md](collection.md#監視チャンネルの発掘) |
