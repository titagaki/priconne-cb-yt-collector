"""収集サイクルのテスト（docs/spec/04）。Discord へも YouTube へも接続しない。"""

from datetime import timedelta

import pytest

from priconne_cb_collector.bot import CollectorBot, Paths
from priconne_cb_collector.store import Store
from tests.support import (
    BOSS_CHANNELS,
    CB_PERIOD,
    FALLBACK_CHANNEL,
    STARTED,
    FakeChannel,
    FakeYouTube,
    bosses_config,
    http_error,
    make_config,
    make_video,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def bot(tmp_path):
    """チャンネルも YouTube も差し替えた Bot。"""
    store = Store(tmp_path / "test.db")
    paths = Paths(
        config=tmp_path / "config.yaml",
        bosses=tmp_path / "bosses.yaml",
        database=tmp_path / "test.db",
    )
    b = CollectorBot(make_config(), bosses_config(), store, "fake-key", paths)
    b.youtube = FakeYouTube()
    b.channels = {cid: FakeChannel(cid) for cid in (*BOSS_CHANNELS.values(), FALLBACK_CHANNEL)}

    async def fetch(channel_id):
        return b.channels.get(channel_id)

    b._fetch_channel = fetch
    yield b
    await b.http_client.aclose()
    store.close()


def sent(bot, channel_id):
    return bot.channels[channel_id].sent


# ---- 収集サイクル ----


async def test_posts_each_video_to_its_boss_channel(bot):
    bot.youtube.videos = [
        make_video("v1", "【プリコネ】ワイバーン 通常凸"),
        make_video("v2", "ライデン 持ち越し35秒"),
    ]
    period = bot.store.open_period(STARTED)

    assert await bot.collect(period, STARTED) == 2

    assert sent(bot, BOSS_CHANNELS[1]) == [
        "【プリコネ】ワイバーン 通常凸\nhttps://www.youtube.com/watch?v=v1"
    ]
    assert sent(bot, BOSS_CHANNELS[3]) == [
        "ライデン 持ち越し35秒\nhttps://www.youtube.com/watch?v=v2"
    ]


async def test_undecided_videos_go_to_the_fallback_channel(bot):
    bot.youtube.videos = [
        make_video("v1", "ワイバーン&ライデン 比較"),  # 複数ヒット
        make_video("v2", "クラバト お疲れさまでした"),  # ヒットなし
    ]
    period = bot.store.open_period(STARTED)

    assert await bot.collect(period, STARTED) == 2
    assert len(sent(bot, FALLBACK_CHANNEL)) == 2


async def test_already_posted_videos_are_not_reposted(bot):
    bot.youtube.videos = [make_video("v1")]
    period = bot.store.open_period(STARTED)
    await bot.collect(period, STARTED)

    assert await bot.collect(period, STARTED) == 0
    assert len(sent(bot, BOSS_CHANNELS[1])) == 1


async def test_ng_words_are_skipped(bot):
    bot.youtube.videos = [
        make_video("v1", "【プリコネ】ワイバーン ガチャ200連"),
        make_video("v2", "ワイバーン 通常凸"),
    ]
    period = bot.store.open_period(STARTED)

    assert await bot.collect(period, STARTED) == 1
    assert bot.store.known_video_ids(["v1", "v2"]) == {"v2"}


async def test_a_failed_post_is_not_recorded_and_retries_next_round(bot):
    """投稿できなかった動画は記録しないので、次の巡回でまた拾われる。"""
    bot.channels[BOSS_CHANNELS[1]].fail_with = http_error(500)
    bot.youtube.videos = [make_video("v1")]
    period = bot.store.open_period(STARTED)

    assert await bot.collect(period, STARTED) == 0
    assert bot.store.known_video_ids(["v1"]) == set()

    bot.channels[BOSS_CHANNELS[1]].fail_with = None
    assert await bot.collect(period, STARTED) == 1


async def test_one_bad_video_does_not_abort_the_round(bot):
    """1件の失敗で収集ジョブ全体を落とさない。"""
    bot.channels[BOSS_CHANNELS[1]].fail_with = RuntimeError("boom")
    bot.youtube.videos = [
        make_video("v1", "ワイバーン 通常凸"),
        make_video("v2", "ライデン 通常凸"),
    ]
    period = bot.store.open_period(STARTED)

    assert await bot.collect(period, STARTED) == 1
    assert bot.store.known_video_ids(["v1", "v2"]) == {"v2"}


async def test_search_failure_returns_zero_instead_of_raising(bot):
    bot.youtube.error = RuntimeError("api down")
    period = bot.store.open_period(STARTED)

    assert await bot.collect(period, STARTED) == 0


async def test_search_query_is_every_boss_name_ored(bot):
    period = bot.store.open_period(STARTED)
    await bot.collect(period, STARTED)

    assert bot.youtube.queries == [
        "ワイバーン OR デミカリド OR ライデン OR スピリットホーン OR オルレオン"
    ]


# ---- ループの制御 ----


async def test_run_once_does_nothing_while_idle(bot):
    assert await bot.run_once(STARTED) == 0
    assert bot.youtube.queries == []


async def test_run_once_respects_the_search_interval(bot):
    bot.youtube.videos = [make_video("v1")]
    bot.store.open_period(STARTED)

    assert await bot.run_once(STARTED) == 1
    bot.youtube.videos = [make_video("v2")]

    # 30分未満では検索しない
    assert await bot.run_once(STARTED + timedelta(minutes=29)) == 0
    assert await bot.run_once(STARTED + timedelta(minutes=31)) == 1


async def test_stale_bosses_yaml_blocks_collection(bot):
    """先月の構成のまま回さない（docs/spec/03）。"""
    bot.bosses = bosses_config(month="2026-06")
    bot.youtube.videos = [make_video("v1")]
    bot.store.open_period(STARTED)

    assert await bot.run_once(STARTED) == 0
    assert bot.youtube.queries == []


async def test_stop_period_closes_and_returns_the_period(bot):
    bot.store.open_period(STARTED)

    period = await bot.stop_period()

    assert period.cb_period == CB_PERIOD
    assert bot.store.current_period() is None
    assert await bot.stop_period() is None
