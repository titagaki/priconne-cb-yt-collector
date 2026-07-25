"""poster.py のテスト（docs/spec/08 §3）。送信先はダミーに差し替える。"""

from datetime import UTC, datetime

from priconne_cb_collector.domain.settings import (
    LAYOUT_PER_BOSS_THREAD,
    LAYOUT_SINGLE,
    AppConfig,
    DiscordConfig,
)
from priconne_cb_collector.interface.poster import REASON_DAILY_LIMIT, Poster
from tests.support import (
    CB_PERIOD,
    FakeBot,
    FakeChannel,
    FakeThreadChannel,
    bosses_config,
    http_error,
    july_period,
    store_video,
)

BOSSES = bosses_config()
NOW = datetime(2026, 7, 26, 6, 0, tzinfo=UTC)  # JST 15:00


def make_poster(store, channel, *, layout=LAYOUT_SINGLE, max_posts_per_boss_per_day=15):
    config = AppConfig(
        discord=DiscordConfig(
            layout=layout,
            channel_id=100,
            max_posts_per_boss_per_day=max_posts_per_boss_per_day,
            post_interval_seconds=0,
        )
    )
    return Poster(FakeBot(channel), config, BOSSES, store)


async def test_pending_videos_are_posted_and_marked(store):
    channel = FakeChannel()
    poster = make_poster(store, channel)
    store_video(store, "vid1")
    store_video(store, "vid2")

    posted = await poster.post_pending(CB_PERIOD, NOW)

    assert posted == 2
    assert len(channel.sent) == 2
    assert store.get_video("vid1")["status"] == "posted"
    assert store.get_video("vid1")["discord_msg_id"] is not None
    assert store.pending_videos(CB_PERIOD) == []


async def test_status_stays_pending_when_discord_fails(store):
    """投稿成功時のみ posted にする（docs/spec/08 §3）。"""
    channel = FakeChannel(fail_with=http_error(500))
    poster = make_poster(store, channel)
    store_video(store, "vid1")

    posted = await poster.post_pending(CB_PERIOD, NOW)

    assert posted == 0
    assert store.get_video("vid1")["status"] == "pending"  # 次回リトライされる


async def test_rate_limit_is_retried_and_the_queue_survives(store):
    """429 を受けても投稿を捨てない（docs/spec/08 §3）。"""

    class RateLimitedOnce(FakeChannel):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def send(self, content=None, embed=None):
            self.attempts += 1
            if self.attempts == 1:
                error = http_error(429)
                error.retry_after = 0
                raise error
            return await super().send(content=content, embed=embed)

    channel = RateLimitedOnce()
    poster = make_poster(store, channel)
    store_video(store, "vid1")

    posted = await poster.post_pending(CB_PERIOD, NOW)

    assert posted == 1
    assert channel.attempts == 2
    assert store.get_video("vid1")["status"] == "posted"


async def test_daily_limit_filters_the_excess(store):
    channel = FakeChannel()
    poster = make_poster(store, channel, max_posts_per_boss_per_day=2)
    for i in range(4):
        store_video(store, f"vid{i}")

    posted = await poster.post_pending(CB_PERIOD, NOW)

    assert posted == 2
    assert store.get_video("vid2")["status"] == "filtered"
    assert store.get_video("vid2")["filter_reason"] == REASON_DAILY_LIMIT
    # 上限到達の通知は1回だけ
    assert len(channel.notices) == 1
    assert "上限" in channel.notices[0]


async def test_daily_limit_is_per_boss(store):
    channel = FakeChannel()
    poster = make_poster(store, channel, max_posts_per_boss_per_day=1)
    store_video(store, "boss1_a", indices=[1])
    store_video(store, "boss1_b", indices=[1])
    store_video(store, "boss2_a", indices=[2])

    await poster.post_pending(CB_PERIOD, NOW)

    assert store.get_video("boss1_a")["status"] == "posted"
    assert store.get_video("boss1_b")["status"] == "filtered"
    assert store.get_video("boss2_a")["status"] == "posted"


async def test_unlimited_when_cap_is_zero(store):
    channel = FakeChannel()
    poster = make_poster(store, channel, max_posts_per_boss_per_day=0)
    for i in range(5):
        store_video(store, f"vid{i}")

    assert await poster.post_pending(CB_PERIOD, NOW) == 5


# ---- ボス別スレッド ----


async def test_boss_threads_are_reused_across_restarts(store):
    channel = FakeThreadChannel()
    poster = make_poster(store, channel, layout=LAYOUT_PER_BOSS_THREAD)
    store.ensure_period(july_period())

    first = await poster.ensure_boss_threads(CB_PERIOD)
    assert len(first) == 5
    assert channel.created[0] == "1ボス: ワイバーン"

    channel.created.clear()
    second = await poster.ensure_boss_threads(CB_PERIOD)
    assert second == first
    assert channel.created == []  # 既存スレッドを作り直さない


async def test_threads_are_not_created_in_single_layout(store):
    channel = FakeThreadChannel()
    poster = make_poster(store, channel, layout=LAYOUT_SINGLE)
    store.ensure_period(july_period())

    assert await poster.ensure_boss_threads(CB_PERIOD) == {}
    assert channel.created == []
