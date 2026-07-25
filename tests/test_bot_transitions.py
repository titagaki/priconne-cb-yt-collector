"""main.py のフェーズ遷移まわりのテスト。Discord へは接続しない。

CollectorBot の poster / collector をダミーに差し替え、_tick_once の副作用
（通知投稿・収集実行・催促）だけを検証する。
"""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from collector import CollectResult
from main import CollectorBot
from models import AppConfig, BossesConfig, DiscordConfig, ScheduleConfig
from schedule import JST
from store import Store

from conftest import SAMPLE_BOSSES


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


def make_bot(tmp_path, *, bosses_month="2026-07", mode="trigger"):
    config = AppConfig(
        schedule=ScheduleConfig(mode=mode),
        discord=DiscordConfig(channel_id=100, post_interval_seconds=0),
    )
    bosses = BossesConfig(month=bosses_month, bosses=SAMPLE_BOSSES)
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


TRAINING_NOW = datetime(2026, 7, 24, 3, 0, tzinfo=timezone.utc)  # JST 7/24 12:00
BATTLE_NOW = datetime(2026, 7, 27, 3, 0, tzinfo=timezone.utc)
AFTER_END = datetime(2026, 7, 31, 3, 0, tzinfo=timezone.utc)


async def start_at(bot, when):
    """/start 相当。以降 current_period() がその期間を返す。"""
    return await bot.start_period(when)


# ---- trigger モード: /start するまで動かない ----

async def test_idle_until_start(bot, monkeypatch):
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await bot._tick_once()

    assert bot.collector.calls == []
    assert bot.poster.threads_created == []


async def test_start_triggers_collection_and_threads(bot, monkeypatch):
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await start_at(bot, TRAINING_NOW)

    await bot._tick_once()

    assert bot.collector.calls  # 収集が走った
    assert bot.poster.threads_created == ["2026-07"]
    assert any("収集を開始" in n for n in bot.poster.notices)


# ---- 前月のボス構成のまま起動しない ----

async def test_stale_bosses_yaml_blocks_collection(tmp_path, monkeypatch):
    bot = make_bot(tmp_path, bosses_month="2026-06")  # 当月は 2026-07
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await start_at(bot, TRAINING_NOW)

    await bot._tick_once()

    assert bot.collector.calls == []
    assert bot.poster.threads_created == []
    assert any("ボス構成が未更新" in n for n in bot.poster.notices)
    bot.store.close()


async def test_collection_resumes_after_bosses_updated(tmp_path, monkeypatch):
    bot = make_bot(tmp_path, bosses_month="2026-06")
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await start_at(bot, TRAINING_NOW)
    await bot._tick_once()
    assert bot.collector.calls == []

    # /reload で当月の構成に差し替わった状況
    bot.bosses = BossesConfig(month="2026-07", bosses=SAMPLE_BOSSES)
    bot._last_phase = None
    await bot._tick_once()

    assert bot.collector.calls
    bot.store.close()


# ---- 遷移通知の重複防止（再起動時） ----

async def test_training_notice_is_not_repeated_after_restart(tmp_path, monkeypatch):
    bot = make_bot(tmp_path)
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await start_at(bot, TRAINING_NOW)
    await bot._tick_once()
    assert sum("収集を開始" in n for n in bot.poster.notices) == 1
    db_path = bot.store.db_path
    bot.store.close()

    # 同じ DB で起動し直す
    restarted = make_bot(tmp_path)
    restarted.store.close()
    restarted.store = Store(db_path)
    restarted.config = replace(
        restarted.config, schedule=replace(restarted.config.schedule, mode="trigger")
    )
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await restarted._tick_once()

    assert not any("収集を開始" in n for n in restarted.poster.notices)
    assert restarted.collector.calls  # 収集自体は再開する
    restarted.store.close()


async def test_battle_transition_announced_once(bot, monkeypatch):
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await start_at(bot, TRAINING_NOW)
    await bot._tick_once()

    monkeypatch.setattr("main.datetime", _FrozenDatetime(BATTLE_NOW))
    await bot._tick_once()
    await bot._tick_once()

    assert sum("本番が始まりました" in n for n in bot.poster.notices) == 1


# ---- 期間終了 ----

async def test_period_end_flushes_queue_then_announces(bot, monkeypatch):
    monkeypatch.setattr("main.datetime", _FrozenDatetime(BATTLE_NOW))
    await start_at(bot, BATTLE_NOW)
    await bot._tick_once()
    bot.poster.posted_calls.clear()

    monkeypatch.setattr("main.datetime", _FrozenDatetime(AFTER_END))
    await bot._tick_once()

    assert any("期間が終了" in n for n in bot.poster.notices)
    assert sum("期間が終了" in n for n in bot.poster.notices) == 1


# ---- /start 催促（11-1 決定） ----

async def test_reminder_posted_once_when_start_forgotten(bot, monkeypatch):
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))

    await bot._tick_once()
    await bot._tick_once()

    reminders = [n for n in bot.poster.notices if "まだ収集が始まっていません" in n]
    assert len(reminders) == 1
    assert "bosses.yaml" in reminders[0]


async def test_no_reminder_before_offset_training_start(bot, monkeypatch):
    early = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)  # トレモ開始(7/23)前
    monkeypatch.setattr("main.datetime", _FrozenDatetime(early))
    await bot._tick_once()
    assert not any("まだ収集が始まっていません" in n for n in bot.poster.notices)


async def test_no_reminder_once_started(bot, monkeypatch):
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await start_at(bot, TRAINING_NOW)
    await bot._tick_once()
    assert not any("まだ収集が始まっていません" in n for n in bot.poster.notices)


# ---- /stop ----

async def test_stop_returns_to_idle(bot, monkeypatch):
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await start_at(bot, TRAINING_NOW)
    await bot._tick_once()
    assert bot.collector.calls

    assert bot.stop_period() is True
    bot.collector.calls.clear()
    await bot._tick_once()
    assert bot.collector.calls == []


# ---- ポーリング間隔 ----

async def test_rss_interval_is_respected(bot, monkeypatch):
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW))
    await start_at(bot, TRAINING_NOW)
    await bot._tick_once()
    assert len(bot.collector.calls) == 1

    # training の RSS 間隔は 20分。1分後の tick では走らない
    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW.replace(minute=1)))
    await bot._tick_once()
    assert len(bot.collector.calls) == 1

    monkeypatch.setattr("main.datetime", _FrozenDatetime(TRAINING_NOW.replace(minute=25)))
    await bot._tick_once()
    assert len(bot.collector.calls) == 2


def _FrozenDatetime(frozen):
    """main.datetime を差し替え、now() だけを固定する。"""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

    return Frozen
