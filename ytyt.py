import os
import argparse
from dotenv import load_dotenv
from googleapiclient.discovery import build

# .envファイルの読み込み
load_dotenv()
API_KEY = os.environ.get("YOUTUBE_API_KEY")

if not API_KEY:
    raise ValueError(".envファイルにYOUTUBE_API_KEYが設定されていません。")

# ボスの定義
BOSS_MAP = {
    1: "ワイバーン",
    2: "デミ・カリド",
    3: "ライデン",
    4: "スピリットホーン",
    5: "オルレオン"
}

# コマンドライン引数の設定
parser = argparse.ArgumentParser(description="YouTubeからボス名で動画を検索")
parser.add_argument("--boss", type=int, choices=[1, 2, 3, 4, 5], help="検索するボスの番号 (1〜5)。指定なしで全ボス。")
args = parser.parse_args()

# 検索クエリの構築 (ボス名のみ)
if args.boss:
    keywords = BOSS_MAP[args.boss]
else:
    # 全ボスのOR検索文字列を構築
    keywords = " OR ".join(BOSS_MAP.values())

# APIの構築
youtube = build("youtube", "v3", developerKey=API_KEY)

# 2026年7月23日以降（UTC時間で指定）
published_after = "2026-07-22T15:00:00Z"

request = youtube.search().list(
    q=keywords,
    part="snippet",
    type="video",
    maxResults=50,
    publishedAfter=published_after,
    order="date",
)

response = request.execute()

# 結果の出力
items = response.get("items", [])
if not items:
    print("条件に一致する動画は見つかりませんでした。")

for item in items:
    title = item["snippet"]["title"]
    video_id = item["id"]["videoId"]
    published_at = item["snippet"]["publishedAt"]
    print(f"タイトル: {title}")
    print(f"URL: https://www.youtube.com/watch?v={video_id}")
    print(f"投稿日: {published_at}\n---")
