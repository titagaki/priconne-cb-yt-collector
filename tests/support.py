"""テスト共通の定数とテストダブル。

各レイヤのテストから import する。フィクスチャは conftest.py 側に置く。
"""

from __future__ import annotations

from datetime import UTC, datetime

import discord

from priconne_cb_collector.domain.models import (
    BATTLE_NORMAL,
    MATCH_BOSS_NAME,
    Boss,
    BossesConfig,
    BossMatch,
    Classification,
    Period,
    VideoMeta,
)
from priconne_cb_collector.domain.schedule import JST

# docs/spec/03 のサンプル構成と同じ（テスト専用。bosses.yaml の正は運用者が管理）
SAMPLE_BOSSES = (
    Boss(1, "ワイバーン", ("ワイバーン", "ワイバン", "wyvern")),
    Boss(2, "デミカリド", ("デミカリド", "デミカリ")),
    Boss(3, "ライデン", ("ライデン", "雷電")),
    Boss(4, "スピリットホーン", ("スピリットホーン", "スピホン")),
    Boss(5, "オルレオン", ("オルレオン", "オルレ")),
)

CB_PERIOD = "2026-07"


def bosses_config(month: str = CB_PERIOD) -> BossesConfig:
    return BossesConfig(month=month, bosses=SAMPLE_BOSSES)


def july_period() -> Period:
    """2026-07 の既定オフセットで算出される期間（トレモ 7/23、本番 7/26〜7/30）。"""
    return Period(
        training_start=datetime(2026, 7, 23, tzinfo=JST),
        battle_start=datetime(2026, 7, 26, tzinfo=JST),
        battle_end=datetime(2026, 7, 30, 23, 59, 59, tzinfo=JST),
        cb_period=CB_PERIOD,
    )


def store_video(
    store,
    video_id: str = "vid1",
    title: str = "【プリコネ】ワイバーン 通常凸",
    **fields,
):
    """判定済みの動画を1件保存し、その行を返す。Embed / 投稿のテスト用。"""
    classification = Classification(
        boss=BossMatch(
            indices=fields.pop("indices", [1]),
            match_source=fields.pop("match_source", MATCH_BOSS_NAME),
            is_summary=fields.pop("is_summary", False),
        ),
        battle_type=fields.pop("battle_type", BATTLE_NORMAL),
        carryover_sec=fields.pop("carryover_sec", None),
        boss_phase=fields.pop("boss_phase", None),
        damage=fields.pop("damage", None),
        is_full_auto=fields.pop("is_full_auto", None),
        is_manual=fields.pop("is_manual", None),
        is_training_footage=fields.pop("is_training_footage", False),
        training_evidence=fields.pop("training_evidence", None),
    )
    video = VideoMeta(
        video_id=video_id,
        title=title,
        channel_id=fields.pop("channel_id", "UC_test"),
        channel_title=fields.pop("channel_title", "テストチャンネル"),
        published_at=fields.pop("published_at", datetime(2026, 7, 26, 5, 0, tzinfo=UTC)),
        discovered_via="rss",
        description=fields.pop("description", "この説明文は Embed に転載してはいけない"),
    )
    store.add_video(
        video,
        classification,
        discovered_phase=fields.pop("discovered_phase", "battle"),
        cb_period=fields.pop("cb_period", CB_PERIOD),
    )
    return store.get_video(video_id)


# 時刻を読むモジュール。now() を固定したいテストはここを差し替える
TIME_READING_MODULES = (
    "priconne_cb_collector.interface.bot",
    "priconne_cb_collector.services.lifecycle",
)


def freeze_now(monkeypatch, frozen: datetime, *modules: str) -> None:
    """指定モジュールの datetime.now() を固定する。"""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

    for module in modules or TIME_READING_MODULES:
        monkeypatch.setattr(f"{module}.datetime", Frozen)


# ---- Discord のテストダブル ----


class FakeMessage:
    def __init__(self, message_id: int):
        self.id = message_id


class FakeChannel:
    """send() を記録するだけのチャンネル。"""

    def __init__(self, channel_id: int = 100, fail_with: Exception | None = None):
        self.id = channel_id
        self.sent: list[tuple[str | None, object]] = []
        self.fail_with = fail_with
        self._next_id = 1000

    async def send(self, content=None, embed=None):
        if self.fail_with is not None:
            raise self.fail_with
        self._next_id += 1
        self.sent.append((content, embed))
        return FakeMessage(self._next_id)

    @property
    def notices(self) -> list[str]:
        return [content for content, _ in self.sent if content]


class FakeThreadChannel(FakeChannel):
    """スレッド作成を記録するチャンネル。"""

    def __init__(self, channel_id: int = 100):
        super().__init__(channel_id)
        self.created: list[str] = []

    async def create_thread(self, name, type=None):
        self._next_id += 1
        self.created.append(name)
        return FakeMessage(self._next_id)


class FakeBot:
    """Poster が要求する get_channel / fetch_channel だけを持つ最小の Bot。"""

    def __init__(self, channel: FakeChannel):
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel

    async def fetch_channel(self, channel_id):
        return self.channel


class _FakeResponse:
    """discord.HTTPException は status を持つオブジェクトを要求する。"""

    def __init__(self, status: int):
        self.status = status
        self.reason = "fake"


def http_error(status: int, message: str = "boom") -> discord.HTTPException:
    return discord.HTTPException(_FakeResponse(status), message)
