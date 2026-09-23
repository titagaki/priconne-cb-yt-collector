# ドキュメント案内

セットアップ・起動・運用手順は [ルート README](../README.md)、エージェント共通の作業ルールは [AGENTS.md](../AGENTS.md) を参照。
まず [進捗と未確認事項](roadmap.md) を確認し、作業に必要な文書を以下から選ぶ。

## 何をどこに書くか

| 文書 | 役割 | 読むときの注意 |
|---|---|---|
| [仕様](spec/README.md) | 現在の Bot の動作・設定・制約の正本 | 実装変更前に該当する節を確認する |
| [設計判断](discussion/README.md) | 理由、却下案、変更の経緯、検証結果 | 廃止済みの記録を含む。現在の要件は仕様で確認する |
| [ゲーム知識](game/README.md) | ゲーム側のルールと動画の表記慣習 | Bot が実装する機能の一覧ではない |
| [参照データ](reference/README.md) | 取得済み HTML、取得条件、データの読み方 | 保存済みデータを保ち、分析結果は設計判断へ書く |
| [進捗](roadmap.md) | 完了状況、次の作業、未確認事項 | 過去の検証結果と今回の確認を区別する |
| `investigations/`（必要時に作成） | 未検証の調査 | 事実と仮説を分け、検証後は該当文書へ移す |

## 作業別の入口

| 作業 | 先に読む仕様 | 実装・検証先 |
|---|---|---|
| スコープの確認 | [01 概要](spec/01-overview.md) | [削減の記録](discussion/reductions.md) |
| 設定・毎月のボス構成 | [05 設定](spec/05-configuration.md) | `config/`、`src/priconne_cb_collector/config.py`、`tests/test_config.py` |
| 開始・停止・再起動 | [03 収集期間](spec/03-schedule.md) | `bot.py`、`store.py`、`tests/test_bot.py`、`tests/test_store.py` |
| 検索・投稿・リトライ | [04 取得と投稿](spec/04-collection.md)、[02 エラー処理](spec/02-architecture.md#4-エラーハンドリング) | `youtube.py`、`bot.py`、`tests/test_bot.py` |
| ボス判定・NG ワード | [04 投稿先と除外](spec/04-collection.md#2-投稿先の決定) | `classify.py`、`tests/test_classify.py`、[参照データ](reference/README.md) |
| DB・ログ・構成 | [02 技術構成](spec/02-architecture.md) | `store.py`、`logging_setup.py`、`tests/test_store.py` |

表内の実装ファイル名は `src/priconne_cb_collector/` 配下。テスト・静的チェックのコマンドは [README](../README.md#テスト) を参照。

## 更新するとき

- 既存の文書に追記できるか確認してから新規文書を作る。新規文書は対応するインデックスからリンクする
- 仕様変更は判断の理由を `discussion/` に記録し、対応する `spec/` と実装・テストを更新する
- 過去の判断は当時の記録として残し、失効した内容を明示する。仕様と実装の相違は未解決事項として記録する
- テスト件数・行数・分析数値には確認日や対象を添える。検証していない項目を完了にしない
