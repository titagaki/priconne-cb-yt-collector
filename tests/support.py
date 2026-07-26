"""テスト共通の定数とテストダブル。フィクスチャは conftest.py 側に置く。"""

from __future__ import annotations

from datetime import UTC, datetime

import discord

from priconne_cb_collector.config import Boss, BossesConfig, Config
from priconne_cb_collector.youtube import Video

CB_PERIOD = "2026-07"
STARTED = datetime(2026, 7, 23, 3, 0, tzinfo=UTC)

# docs/spec/05 のサンプル構成と同じ（テスト専用。bosses.yaml の正は運用者が管理）
SAMPLE_BOSSES = (
    Boss(1, "ワイバーン", ("ワイバーン", "ワイバン", "wyvern")),
    Boss(2, "デミカリド", ("デミカリド", "デミカリ")),
    Boss(3, "ライデン", ("ライデン", "雷電")),
    Boss(4, "スピリットホーン", ("スピリットホーン", "スピホン")),
    Boss(5, "オルレオン", ("オルレオン", "オルレ")),
)

FALLBACK_CHANNEL = 900
BOSS_CHANNELS = {1: 101, 2: 102, 3: 103, 4: 104, 5: 105}


def bosses_config(month: str = CB_PERIOD) -> BossesConfig:
    return BossesConfig(month=month, bosses=SAMPLE_BOSSES)


def make_config(**overrides) -> Config:
    defaults = dict(
        search_interval_minutes=30,
        search_lookback_days=1,
        title_ng_words=("ガチャ", "雑談"),
        post_interval_seconds=0,  # テストで待たない
        boss_channels=dict(BOSS_CHANNELS),
        fallback_channel_id=FALLBACK_CHANNEL,
    )
    defaults.update(overrides)
    return Config(**defaults)


def make_video(video_id: str = "vid1", title: str = "【プリコネ】ワイバーン 通常凸") -> Video:
    return Video(
        video_id=video_id,
        title=title,
        published_at=datetime(2026, 7, 26, 5, 0, tzinfo=UTC),
        channel_title="テストチャンネル",
    )


class FakeYouTube:
    """search() の戻り値を差し替えるだけのクライアント。"""

    def __init__(self, videos: list[Video] | None = None, error: Exception | None = None):
        self.videos = videos or []
        self.error = error
        self.queries: list[str] = []

    async def search(self, query, published_after, max_results=50):
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return list(self.videos)


class FakeMessage:
    def __init__(self, message_id: int):
        self.id = message_id


class FakeChannel:
    """send() を記録するだけのチャンネル。"""

    def __init__(self, channel_id: int, fail_with: Exception | None = None):
        self.id = channel_id
        self.sent: list[str] = []
        self.fail_with = fail_with
        self._next_id = 1000

    async def send(self, content=None):
        if self.fail_with is not None:
            raise self.fail_with
        self._next_id += 1
        self.sent.append(content)
        return FakeMessage(self._next_id)


class _FakeResponse:
    """discord.HTTPException は status を持つオブジェクトを要求する。"""

    def __init__(self, status: int):
        self.status = status
        self.reason = "fake"


def http_error(status: int, message: str = "boom") -> discord.HTTPException:
    return discord.HTTPException(_FakeResponse(status), message)
