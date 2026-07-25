# 12. 実装順序の推奨

1. 設定読み込み + バリデーション + 期間判定（`schedule.py`）とそのテスト → [03](03-configuration.md), [04](04-schedule.md)
2. 判定ロジック（`classify/`）とテスト ← **YouTube にも Discord にも繋がずに完結する。ここを先に固めること** → [06](06-classification.md)
3. SQLite 永続化 → [07](07-persistence.md)
4. RSS 取得 → 判定 → DB 保存（Discord 投稿はログ出力でモック） → [05](05-collection.md)
5. Discord 投稿 → [08](08-discord-posting.md)
6. Data API 検索 + クォータ管理 → [05](05-collection.md)
7. スラッシュコマンド → [09](09-slash-commands.md)

着手前に [11. 未確定事項](11-open-questions.md) の確認を済ませること。
進捗は `docs/roadmap.md` で管理する。
