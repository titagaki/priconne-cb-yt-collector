"""プリコネ クラバト攻略動画の収集 Bot。

レイヤ構成（依存は上から下への一方向）:

    interface/  Discord 配信層（スラッシュコマンド、Embed、投稿キュー、Bot 本体）
    services/   ユースケース（収集パイプライン、期間ライフサイクル）
    adapters/   外部 I/O（SQLite、YouTube Data API、設定ファイル）
    domain/     依存なし。dataclass と純粋関数（判定ロジック、期間計算）

仕様の正は docs/spec/ 配下。
"""

__version__ = "0.1.0"
