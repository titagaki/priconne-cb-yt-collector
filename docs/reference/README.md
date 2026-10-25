# 参照データ

判定ロジックの検証に使う取得済みデータ。取得結果を HTML に整形し、`off` クラスなどの注記を付けて保存している。
**保存済みのデータは検証用の入力として保持し、分析結果は [設計判断](../discussion/README.md) に記録する。**

| ファイル | 内容 |
|---|---|
| [priconne_cb_2026-07_full.html](priconne_cb_2026-07_full.html) | 2026年7月クラバトの5ボスについて、**ボス名のみ**で YouTube を検索した全126件。無関係な動画（ARK、Dark and Darker など）も `off` クラスつきで含む |
| [priconne_cb_2026-08_full.html](priconne_cb_2026-08_full.html) | 2026年8月クラバトの5ボスについて、**ボス名のみ**で検索した全224件（延べ、ユニーク208件。2026-08-26 取得、`publishedAfter=2026-08-01` JST、ボスごと最大3ページ）。無関係な動画（ギリシャ神話、城ドラ、FF3 など）も `off` クラスつきで含む |
| [priconne_cb_2026-08_update-0826.html](priconne_cb_2026-08_update-0826.html) | 上を 08-25 に取ったときとの差分。`video_id` で前回分を除いた新規70件（延べ80件）だけを同じ体裁で並べたもの |
| [priconne_cb_2026-09_full.html](priconne_cb_2026-09_full.html) | 2026年9月の5ボス。2026-09-23 12:33 JST 取得、9月1日 JST 以降、正式名ごと最大3ページ（実際は各1ページ）。延べ41件・ユニーク40件。関連は暫定で延べ33件・ユニーク32件 |
| [priconne_cb_2026-09_search.json](priconne_cb_2026-09_search.json) | 9月のAPI取得データ、検索条件、ページ数、取得日時、暫定判定の対象ID |
| [priconne_cb_2026-09_update-0924.html](priconne_cb_2026-09_update-0924.html) | 9月24日21:55 JST取得。前回9月23日12:33:16 JST以降を検索し、既存IDを除外した新規22件（ボス別延べ29件）。関連は暫定21件（延べ28件） |
| [priconne_cb_2026-09_update-0924_search.json](priconne_cb_2026-09_update-0924_search.json) | 更新分のAPI取得データ（既存IDも保持）、取得条件・日時、ボス別新規ID、暫定判定 |
| [priconne_cb_2026-10_full.html](priconne_cb_2026-10_full.html) | 2026年10月の5ボス。10月24日18:54 JST取得、運用者指定の10月23日12:00 JST以降を正式名ごとに検索。各1ページ、次ページなし。延べ28件・ユニーク27件、全件を暫定で関連と判定 |
| [priconne_cb_2026-10_search.json](priconne_cb_2026-10_search.json) | 10月のAPI取得データ、検索条件、ページ数、取得日時、暫定判定。検索5回（既存の見積もりで500ユニット） |
| [priconne_cb_2026-10_update-1025.html](priconne_cb_2026-10_update-1025.html) | 10月25日23:36 JST取得。前回10月24日18:54:13 JST以降を検索し、既存IDを除外した新規12件（ボス別延べ18件）。全件を暫定で関連と判定。「プリコネ関連のみ表示」を維持 |
| [priconne_cb_2026-10_update-1025_search.json](priconne_cb_2026-10_update-1025_search.json) | 更新分のAPI取得データ（既存IDも保持）、取得条件・日時、ボス別新規ID、暫定判定 |

9月・10月版の関連判定はタイトル・チャンネル名・説明文による暫定判定で、本編は未確認。月途中の取得結果であり、月全体の網羅を保証しない。

`off` が付いていない行がクラバト関連として分類された動画。この正例・負例の両方が入っている点が重要で、
取りこぼしだけでなく誤爆も測れる。

検証結果は [discussion/判定ロジック](../discussion/classification.md#実データによる検証2026-07-26)
と [discussion/動画の取得](../discussion/collection.md#検索はボス名だけで行う) に記録している。

## 2026-08 で分かったこと

分析結果は [判定ロジックの検証記録](../discussion/classification.md#2026-08-の参照データによる検証) に移した。
