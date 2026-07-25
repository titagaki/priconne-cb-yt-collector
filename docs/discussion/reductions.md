# 削減の記録

実装が一巡したあと、要件に無い機能を削除した記録。

## 2026-07-26: フェーズの2値化と段階の削除

運用者の判断による。実装 3,025行 / テスト 2,186行の状態からの削減。

| 削除したもの | 理由 |
|---|---|
| トレモ期間 / 本番期間の区別（3状態 → 2状態） | [収集期間](schedule.md#状態を収集する--しないの2値にした理由) |
| ボスの「段階」抽出（`boss_phase`） | [判定ロジック](classification.md#ボスの段階) |
| `training_evidence` の2値（`keyword` / `phase_only`） | 期間の区別が消えて `phase_only` が成立しなくなった。`is_training_footage: bool` に集約 |
| 本番開始通知 | 運用者はゲーム内で本番開始を知っている |
| ポーリング間隔の期間別分岐（設定5項目 → 3項目） | 上記に伴い統一。RSS 30分 / API 検索 3時間 |
| `schedule.training_days_before` | `start_offset_days` に統合（5 + 3 → 8）。計算結果は不変 |
| `manual_training_start` / `manual_battle_start` | `manual_start` に統合 |

### DB スキーマへの影響

削除された列:

- `videos.discovered_phase` / `videos.boss_phase` / `videos.training_evidence`
- `period_state.battle_start` / `period_state.notified_battle`

改名された列:

- `period_state.training_start` → `start_at`、`period_state.battle_end` → `end_at`
- `period_state.notified_training` → `notified_start`

**既存の `data/bot.db` とは互換性がない。** 実運用前のため移行スクリプトは用意せず、
DB ファイルを作り直す前提とした。

### 検討したが削除しなかったもの

| 候補 | 残した理由 |
|---|---|
| ETag / 304 対応 | 実装コストが小さく、無駄な取得を減らす実利がある |
| 429 リトライ | レート制限時の取りこぼし耐性。目的に直結する |
| `damage` / `is_full_auto` / `is_manual` の抽出 | 段階と違い、動画を選ぶ判断材料として機能している |
| 待機中のポーリングループ | 止めると `offset`/`manual` の自動開始と `/start` 催促が同時に死ぬ。[収集期間](schedule.md#待機中もポーリングループを回している理由) |

### まだ判断していない削減候補

以下は候補として挙げたが、採否を決めていない。

- API 検索（経路B）+ クォータ管理 + `/suggest_channels`（RSS のみに絞る案）
- `offset` / `manual` モードと `/period set`（`trigger` 固定にする案）
- 設定フラグの固定値化（`layout` の `single`、`enable_ex_notation`、`on_boss_unknown`）
- `/recent` / `/bosses` / `/collect` / `/stop` / `/reload` の整理
- `videos.view_count`（取得・保存しているが未使用）
- まとめ動画の `is_summary` 別扱い
