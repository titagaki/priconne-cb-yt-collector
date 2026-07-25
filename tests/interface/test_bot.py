"""interface/bot.py の収集開始 / 終了まわりのテスト。Discord へは接続しない。

CollectorBot の poster / collector をダミーに差し替え、_tick_once の副作用
（通知投稿・収集実行・催促）だけを検証する。
"""

from datetime import UTC, datetime

import pytest

from priconne_cb_collector.adapters.sqlite_store import Store
from priconne_cb_collector.domain.settings import (
    MODE_TRIGGER,
    AppConfig,
    DiscordConfig,
    ScheduleConfig,
)
from priconne_cb_collector.interface.bot import CollectorBot
from priconne_cb_collector.services.collection import CollectResult
from tests.support import CB_PERIOD, bosses_config, freeze_now


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

    async def collect(self, period, now=None, run_api_search=False):
        self.calls.append((period.cb_period, run_api_search))
        return CollectResult(fetched=0, new=0)


def make_bot(tmp_path, *, bosses_month=CB_PERIOD, mode=MODE_TRIGGER):
    config = AppConfig(
        schedule=ScheduleConfig(mode=mode),
        discord=DiscordConfig(channel_id=100, post_interval_seconds=0),
    )
    bosses = bosses_config(bosses_month)
    store = Store(tmp_path / "bot.db")
    bot = CollectorBot(config, bosses, store, api_key=None)
    bot.poster = FakePoster()
    bot.collector = FakeCollector()
    return bot


@pytest.fixture
def bot(tmp_path):
    b = make_bot(tmp_path)
    yield b
    b.store.close()


IN_PERIOD = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)  # JST 7/24 12:00
LATER_IN_PERIOD = datetime(2026, 7, 27, 3, 0, tzinfo=UTC)
AFTER_END = datetime(2026, 7, 31, 3, 0, tzinfo=UTC)


async def start_at(bot, when):
    """/start 相当。以降 current_period() がその期間を返す。"""
    return await bot.start_period(when)


# ---- trigger モード: /start するまで動かない ----


async def test_idle_until_start(bot, monkeypatch):
    freeze_now(monkeypatch, IN_PERIOD)
    await bot._tick_once()

    assert bot.collector.calls == []
    assert bot.poster.threads_created == []


async def test_start_triggers_collection_and_threads(bot, monkeypatch):
    freeze_now(monkeypatch, IN_PERIOD)
    await start_at(bot, IN_PERIOD)

    await bot._tick_once()

    assert bot.collector.calls  # 収集が走った
    assert bot.poster.threads_created == [CB_PERIOD]
    assert any("収集を開始" in n for n in bot.poster.notices)


# ---- 前月のボス構成のまま起動しない ----


async def test_stale_bosses_yaml_blocks_collection(tmp_path, monkeypatch):
    bot = make_bot(tmp_path, bosses_month="2026-06")  # 当月は 2026-07
    freeze_now(monkeypatch, IN_PERIOD)
    await start_at(bot, IN_PERIOD)

    await bot._tick_once()

    assert bot.collector.calls == []
    assert bot.poster.threads_created == []
    assert any("ボス構成が未更新" in n for n in bot.poster.notices)
    bot.store.close()


async def test_collection_resumes_after_bosses_updated(tmp_path, monkeypatch):
    bot = make_bot(tmp_path, bosses_month="2026-06")
    freeze_now(monkeypatch, IN_PERIOD)
    await start_at(bot, IN_PERIOD)
    await bot._tick_once()
    assert bot.collector.calls == []

    # /reload で当月の構成に差し替わった状況
    bot.bosses = bosses_config()
    bot._was_collecting = None
    await bot._tick_once()

    assert bot.collector.calls
    bot.store.close()


# ---- 遷移通知の重複防止（再起動時） ----


async def test_start_notice_is_not_repeated_after_restart(tmp_path, monkeypatch):
    bot = make_bot(tmp_path)
    freeze_now(monkeypatch, IN_PERIOD)
    await start_at(bot, IN_PERIOD)
    await bot._tick_once()
    assert sum("収集を開始" in n for n in bot.poster.notices) == 1
    bot.store.close()

    # 同じ DB ファイルで起動し直す（/start 済みの状態が DB から復元される）
    restarted = make_bot(tmp_path)
    await restarted._tick_once()

    assert not any("収集を開始" in n for n in restarted.poster.notices)
    assert restarted.collector.calls  # 収集自体は再開する
    restarted.store.close()


# ---- 期間終了 ----


async def test_period_end_flushes_queue_then_announces(bot, monkeypatch):
    freeze_now(monkeypatch, LATER_IN_PERIOD)
    await start_at(bot, LATER_IN_PERIOD)
    await bot._tick_once()
    bot.poster.posted_calls.clear()

    freeze_now(monkeypatch, AFTER_END)
    await bot._tick_once()

    assert any("期間が終了" in n for n in bot.poster.notices)
    assert sum("期間が終了" in n for n in bot.poster.notices) == 1


# ---- /start 催促（11-1 決定） ----


async def test_reminder_posted_once_when_start_forgotten(bot, monkeypatch):
    freeze_now(monkeypatch, IN_PERIOD)

    await bot._tick_once()
    await bot._tick_once()

    reminders = [n for n in bot.poster.notices if "まだ収集が始まっていません" in n]
    assert len(reminders) == 1
    assert "bosses.yaml" in reminders[0]


async def test_no_reminder_before_offset_start(bot, monkeypatch):
    early = datetime(2026, 7, 20, 3, 0, tzinfo=UTC)  # 収集開始(7/23)前
    freeze_now(monkeypatch, early)
    await bot._tick_once()
    assert not any("まだ収集が始まっていません" in n for n in bot.poster.notices)


async def test_no_reminder_once_started(bot, monkeypatch):
    freeze_now(monkeypatch, IN_PERIOD)
    await start_at(bot, IN_PERIOD)
    await bot._tick_once()
    assert not any("まだ収集が始まっていません" in n for n in bot.poster.notices)


# ---- /stop ----


async def test_stop_returns_to_idle(bot, monkeypatch):
    freeze_now(monkeypatch, IN_PERIOD)
    await start_at(bot, IN_PERIOD)
    await bot._tick_once()
    assert bot.collector.calls

    assert bot.stop_period() is True
    bot.collector.calls.clear()
    await bot._tick_once()
    assert bot.collector.calls == []


# ---- ポーリング間隔 ----


async def test_rss_interval_is_respected(bot, monkeypatch):
    freeze_now(monkeypatch, IN_PERIOD)
    await start_at(bot, IN_PERIOD)
    await bot._tick_once()
    assert len(bot.collector.calls) == 1

    # RSS 間隔は 30分。1分後の tick では走らない
    freeze_now(monkeypatch, IN_PERIOD.replace(minute=1))
    await bot._tick_once()
    assert len(bot.collector.calls) == 1

    freeze_now(monkeypatch, IN_PERIOD.replace(minute=35))
    await bot._tick_once()
    assert len(bot.collector.calls) == 2


# ---- ポーリング間隔の切り替え（roadmap 監査 A） ----


async def test_tick_slows_down_while_idle(bot, monkeypatch):
    """idle 中は idle_check_interval_minutes 間隔に落とす（docs/spec/04 §3）。"""
    freeze_now(monkeypatch, IN_PERIOD)
    await bot._tick_once()

    assert bot.tick.seconds == bot.config.polling.idle_check_interval_minutes * 60


async def test_tick_returns_to_short_interval_once_running(bot, monkeypatch):
    freeze_now(monkeypatch, IN_PERIOD)
    await bot._tick_once()  # idle でいったん遅くなる
    assert bot.tick.seconds > 60

    await start_at(bot, IN_PERIOD)  # /start は即座に間隔を戻す
    assert bot.tick.seconds == 60

    await bot._tick_once()
    assert bot.tick.seconds == 60


async def test_stop_slows_the_tick_again(bot, monkeypatch):
    freeze_now(monkeypatch, IN_PERIOD)
    await start_at(bot, IN_PERIOD)
    await bot._tick_once()
    assert bot.tick.seconds == 60

    bot.stop_period()
    assert bot.tick.seconds == bot.config.polling.idle_check_interval_minutes * 60


# ---- 収集期間外の /collect（roadmap 監査 C） ----


async def test_manual_collect_is_refused_outside_the_period(bot, monkeypatch):
    """cb_period が決まらないため、収集期間外の /collect は拒否する。"""
    freeze_now(monkeypatch, IN_PERIOD)

    with pytest.raises(RuntimeError, match="収集期間外"):
        await bot.run_collection()

    assert bot.collector.calls == []


async def test_manual_collect_runs_inside_the_period(bot, monkeypatch):
    freeze_now(monkeypatch, IN_PERIOD)
    await start_at(bot, IN_PERIOD)

    await bot.run_collection(run_api_search=True)

    assert bot.collector.calls == [(CB_PERIOD, True)]
    assert bot.poster.posted_calls == [CB_PERIOD]
