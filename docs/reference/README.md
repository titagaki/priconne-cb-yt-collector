# 参照データ

判定ロジックの検証に使う実データ。**加工せず取得したままを置く。**

| ファイル | 内容 |
|---|---|
| [priconne_cb_2026-07_full.html](priconne_cb_2026-07_full.html) | 2026年7月クラバトの5ボスについて、**ボス名のみ**で YouTube を検索した全126件。無関係な動画（ARK、Dark and Darker など）も `off` クラスつきで含む |

`off` が付いていない行がクラバト攻略動画。この正例・負例の両方が入っている点が重要で、
取りこぼしだけでなく誤爆も測れる。

検証結果は [discussion/判定ロジック](../discussion/classification.md#実データによる検証2026-07-26)
と [discussion/動画の取得](../discussion/collection.md#検索はボス名だけで行う) に記録している。
