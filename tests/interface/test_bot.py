"""interface/bot.py の収集開始 / 終了まわりのテスト。Discord へは接続しない。

CollectorBot の poster / collector をダミーに差し替え、_tick_once と
/start・/stop の副作用（通知投稿・収集実行・ループの起動停止）だけを検証する。
"""

from datetime import UTC, datetime

import pytest

from priconne_cb_collector.adapters.sqlite_store import Store
from priconne_cb_collector.domain.settings import AppConfig, DiscordConfig
from priconne_cb_collector.interface.bot import CollectorBot
from priconne_cb_collector.services.collection import CollectResult
from tests.support import CB_PERIOD, bosses_config, freeze_now, store_video


class FakePoster:
    def __init__(self):
        self.notices = []
        self.threads_created = []
        self.posted_calls = []
        self.config = None
        self.bosses = None

    async def send_notice(self, content="", embed=None):
        self.notices.append(content or (embed.title if embed else ""))
        return object()

    async def ensure_boss_threads(self, cb_period):
        self.threads_created.append(cb_period)
        return {i: 1000 + i for i in range(1, 6)}

    async def post_pending(self, cb_period, now=None):
        self.posted_calls.append(cb_period)
        return 0

    def reset_daily_limit_notices(self):
        pass


class FakeCollector:
    def __init__(self):
        self.calls = []
        self.config = None
        self.bosses = None

    async def collect(self, period, now=None):
        self.calls.append(period.cb_period)
        return CollectResult(fetched=0, new=0)


def make_bot(tmp_path, *, bosses_month=CB_PERIOD):
    config = AppConfig(discord=DiscordConfig(channel_id=100, post_interval_seconds=0))
    bosses = bosses_config(bosses_month)
    store = Store(tmp_path / "bot.db")
    bot = CollectorBot(config, bosses, store, api_key=None)
    bot.poster = FakePoster()
    bot.collector = FakeCollector()
    # The real discord.ext task needs a logged-in client; record the intent instead
    # and drive _tick_once by hand.
    bot.loop_calls = []
    bot._resume_loop = lambda: bot.loop_calls.append("resume")
    bot._park_loop = lambda: bot.loop_calls.append("park")
    return bot


@pytest.fixture
def bot(tmp_path):
    b = make_bot(tmp_path)
    yield b
    b.store.close()


STARTED = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)  # JST 7/24 12:00
LATER = datetime(2026, 7, 27, 3, 0, tzinfo=UTC)
NEXT_MONTH = datetime(2026, 8, 3, 3, 0, tzinfo=UTC)


# ---- /start するまで動かない ----


async def test_idle_until_start(bot, monkeypatch):
    freeze_now(monkeypatch, STARTED)
    await bot._tick_once()

    assert bot.collector.calls == []
    assert bot.poster.threads_created == []


async def test_start_triggers_collection_and_threads(bot, monkeypatch):
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)

    await bot._tick_once()

    assert bot.collector.calls  # 収集が走った
    assert bot.poster.threads_created == [CB_PERIOD]
    # 開始を知らせるのは /start の返信だけ。ループは何も投稿しない（docs/spec/04 §3）
    assert bot.poster.notices == []


async def test_collection_continues_into_the_next_month(bot, monkeypatch):
    """終了日が無いので、月をまたいでも /stop まで収集し続ける。"""
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)
    await bot._tick_once()

    freeze_now(monkeypatch, NEXT_MONTH)
    bot.collector.calls.clear()
    await bot._tick_once()

    assert bot.collector.calls == [CB_PERIOD]  # 開始月のキーのまま


# ---- 前月のボス構成のまま起動しない ----


async def test_stale_bosses_yaml_blocks_collection(tmp_path, monkeypatch):
    bot = make_bot(tmp_path, bosses_month="2026-06")  # 当月は 2026-07
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)

    await bot._tick_once()

    assert bot.collector.calls == []
    assert bot.poster.threads_created == []
    assert any("ボス構成が未更新" in n for n in bot.poster.notices)
    bot.store.close()


async def test_collection_resumes_after_bosses_updated(tmp_path, monkeypatch):
    bot = make_bot(tmp_path, bosses_month="2026-06")
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)
    await bot._tick_once()
    assert bot.collector.calls == []

    # /reload で当月の構成に差し替わった状況
    bot.bosses = bosses_config()
    bot._was_collecting = None
    await bot._tick_once()

    assert bot.collector.calls
    bot.store.close()


# ---- 再起動時は黙って再開する ----


async def test_restart_resumes_collection_without_announcing(tmp_path, monkeypatch):
    bot = make_bot(tmp_path)
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)
    await bot._tick_once()
    bot.store.close()

    # 同じ DB ファイルで起動し直す（収集中の状態が DB から復元される）
    restarted = make_bot(tmp_path)
    await restarted._tick_once()

    assert restarted.poster.notices == []  # 通知フラグを持たずに黙る
    assert restarted.collector.calls  # 収集自体は再開する
    assert restarted.poster.threads_created == [CB_PERIOD]  # スレッドは確認し直す
    restarted.store.close()


# ---- /stop ----


async def test_stop_flushes_queue_then_announces(bot, monkeypatch):
    """終了は /stop だけ。未投稿分を投げ切ってから総括を出す（11-4 決定）。"""
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)
    await bot._tick_once()
    store_video(bot.store)  # 投稿待ちの動画が残っている状態
    bot.poster.posted_calls.clear()

    freeze_now(monkeypatch, LATER)
    assert await bot.stop_period() is True

    assert bot.poster.posted_calls == [CB_PERIOD]  # 投げ切ってから
    assert sum("収集を終了" in n for n in bot.poster.notices) == 1


async def test_stop_returns_to_idle(bot, monkeypatch):
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)
    await bot._tick_once()
    assert bot.collector.calls

    assert await bot.stop_period() is True
    bot.collector.calls.clear()
    await bot._tick_once()
    assert bot.collector.calls == []


async def test_stop_when_idle_reports_nothing_to_stop(bot, monkeypatch):
    freeze_now(monkeypatch, STARTED)
    assert await bot.stop_period() is False
    assert bot.poster.notices == []


# ---- ポーリングループの起動 / 停止（催促を廃止したため待機中は回さない） ----


async def test_loop_runs_only_while_collecting(bot, monkeypatch):
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)
    await bot.stop_period()

    assert bot.loop_calls == ["resume", "park"]


async def test_tick_parks_the_loop_if_the_period_vanishes(bot, monkeypatch):
    """/stop を経ずに期間が消えても、ループは自分で止まる。"""
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)
    bot.store.close_period(CB_PERIOD)
    bot.loop_calls.clear()

    await bot._tick_once()

    assert bot.loop_calls == ["park"]
    assert bot.collector.calls == []


# ---- ポーリング間隔 ----


async def test_search_interval_is_respected(bot, monkeypatch):
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)
    await bot._tick_once()
    assert len(bot.collector.calls) == 1

    # 検索間隔は 30分。1分後の tick では走らない
    freeze_now(monkeypatch, STARTED.replace(minute=1))
    await bot._tick_once()
    assert len(bot.collector.calls) == 1

    freeze_now(monkeypatch, STARTED.replace(minute=35))
    await bot._tick_once()
    assert len(bot.collector.calls) == 2


# ---- 収集期間外の /collect（roadmap 監査 C） ----


async def test_manual_collect_is_refused_outside_the_period(bot, monkeypatch):
    """cb_period が決まらないため、収集していないときの /collect は拒否する。"""
    freeze_now(monkeypatch, STARTED)

    with pytest.raises(RuntimeError, match="収集期間外"):
        await bot.run_collection()

    assert bot.collector.calls == []


async def test_manual_collect_runs_inside_the_period(bot, monkeypatch):
    freeze_now(monkeypatch, STARTED)
    await bot.start_period(STARTED)

    await bot.run_collection()

    assert bot.collector.calls == [CB_PERIOD]
    assert bot.poster.posted_calls == [CB_PERIOD]
