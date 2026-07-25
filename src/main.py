"""Entry point: bot startup, polling loop and phase transitions (docs/spec/04)."""
from __future__ import annotations

import logging
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import discord
import httpx
from discord.ext import tasks
from dotenv import load_dotenv

from collector import Collector
from config import load_bosses, load_config
from discord_bot.commands import setup_commands
from discord_bot.poster import Poster
from logging_setup import setup_logging
from models import PHASE_BATTLE, PHASE_IDLE, PHASE_TRAINING, Period
from schedule import JST, phase_at, resolve_period, should_remind
from sources.youtube_api import YouTubeClient
from store import Store

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config/config.yaml")
BOSSES_PATH = Path("config/bosses.yaml")
DB_PATH = Path("data/bot.db")
TICK_SECONDS = 60


class CollectorBot(discord.Client):
    def __init__(self, config, bosses, store: Store, api_key: str | None):
        super().__init__(intents=discord.Intents.default())
        self.tree = discord.app_commands.CommandTree(self)
        self.config = config
        self.bosses = bosses
        self.store = store
        self.api_key = api_key

        self.http_client = httpx.AsyncClient(headers={"User-Agent": "priconne-cb-yt-collector/0.1"})
        youtube = YouTubeClient(self.http_client, api_key) if api_key else None
        if youtube is None:
            logger.warning("YOUTUBE_API_KEY is not set; running with rss only")
        self.collector = Collector(config, bosses, store, self.http_client, youtube)
        self.poster = Poster(self, config, bosses, store)

        self._last_rss: datetime | None = None
        self._last_api: datetime | None = None
        self._last_phase: str | None = None
        self._threads_ready = False

    # ---- period / phase ----

    def current_period(self) -> Period | None:
        started = None
        if self.config.schedule.mode == "trigger":
            started = self._stored_trigger_start()
        return resolve_period(self.config.schedule, datetime.now(timezone.utc), started)

    def _stored_trigger_start(self) -> datetime | None:
        """Look up the /start time. The period key comes from the offset calendar."""
        now = datetime.now(JST)
        for cb_period in _candidate_periods(now):
            started = self.store.trigger_started_at(cb_period)
            if started is not None:
                return started
        return None

    def current_phase(self, now: datetime | None = None) -> str:
        return phase_at(now or datetime.now(timezone.utc), self.current_period())

    async def start_period(self, now: datetime) -> Period:
        """/start: begin collecting immediately from this moment."""
        sched = replace(self.config.schedule, mode="trigger")
        period = resolve_period(sched, now, trigger_started_at=now)
        self.store.set_trigger_start(period)
        self.config = replace(self.config, schedule=sched)
        self.collector.config = self.config
        self.poster.config = self.config
        self._last_phase = None  # let the tick emit the training announcement
        self._threads_ready = False
        logger.info("period started manually: cb_period=%s", period.cb_period)
        return period

    def stop_period(self) -> bool:
        period = self.current_period()
        if period is None:
            return False
        self.store.clear_trigger_start(period.cb_period)
        self._last_phase = PHASE_IDLE
        self._threads_ready = False
        logger.info("period stopped manually: cb_period=%s", period.cb_period)
        return True

    def set_manual_period(self, training_start, battle_start, end) -> Period:
        sched = replace(
            self.config.schedule,
            mode="manual",
            manual_training_start=training_start,
            manual_battle_start=battle_start,
            manual_end=end,
        )
        period = resolve_period(sched, datetime.now(timezone.utc))
        if period is None:
            raise ValueError("期間を解釈できませんでした")
        self.config = replace(self.config, schedule=sched)
        self.collector.config = self.config
        self.poster.config = self.config
        self.store.ensure_period(period)
        self._last_phase = None
        self._threads_ready = False
        logger.info("period overridden manually: cb_period=%s", period.cb_period)
        return period

    def reload_config(self) -> None:
        self.config = load_config(CONFIG_PATH)
        self.bosses = load_bosses(BOSSES_PATH)
        self.collector.config = self.config
        self.collector.bosses = self.bosses
        self.poster.config = self.config
        self.poster.bosses = self.bosses
        logger.info("config reloaded: bosses_month=%s", self.bosses.month)

    # ---- lifecycle ----

    async def setup_hook(self) -> None:
        setup_commands(self)
        await self.tree.sync()
        self.tick.start()

    async def on_ready(self) -> None:
        logger.info("logged in: user=%s", self.user)

    async def close(self) -> None:
        await self.http_client.aclose()
        await super().close()

    # ---- polling loop ----

    @tasks.loop(seconds=TICK_SECONDS)
    async def tick(self) -> None:
        try:
            await self._tick_once()
        except Exception:
            logger.exception("tick failed")

    @tick.before_loop
    async def before_tick(self) -> None:
        await self.wait_until_ready()

    async def _tick_once(self) -> None:
        now = datetime.now(timezone.utc)
        period = self.current_period()
        phase = phase_at(now, period)

        if period is None:
            await self._maybe_remind(now)
            self._last_phase = phase
            return

        self.store.ensure_period(period)

        if phase != self._last_phase:
            await self._handle_transition(self._last_phase, phase, period, now)
            self._last_phase = phase

        if phase == PHASE_IDLE:
            await self._maybe_remind(now)
            return

        if not self._month_matches():
            return  # a stale bosses.yaml already triggered the warning below

        await self._run_due_collections(phase, period, now)
        await self.poster.post_pending(period.cb_period, now)

    async def _run_due_collections(self, phase: str, period: Period, now: datetime) -> None:
        polling = self.config.polling
        if phase == PHASE_TRAINING:
            rss_minutes = polling.training_rss_interval_minutes
            api_hours = polling.training_api_search_interval_hours
        else:
            rss_minutes = polling.rss_interval_minutes
            api_hours = polling.api_search_interval_hours

        rss_due = self._last_rss is None or (now - self._last_rss).total_seconds() >= rss_minutes * 60
        api_due = self._last_api is None or (now - self._last_api).total_seconds() >= api_hours * 3600
        if not rss_due and not api_due:
            return

        result = await self.collector.collect(period, now=now, run_api_search=api_due)
        self._last_rss = now
        if api_due and not result.api_search_skipped:
            self._last_api = now

    async def _handle_transition(
        self, previous: str | None, phase: str, period: Period, now: datetime
    ) -> None:
        if phase == PHASE_TRAINING:
            if not self._month_matches():
                await self._warn_stale_bosses(period)
                return
            if self.store.mark_notified(period.cb_period, "training"):
                await self._announce_training(period)
            await self._ensure_threads(period)
        elif phase == PHASE_BATTLE:
            if not self._month_matches():
                await self._warn_stale_bosses(period)
                return
            await self._ensure_threads(period)
            if self.store.mark_notified(period.cb_period, "battle"):
                await self.poster.send_notice(
                    f"**クラバト本番が始まりました**（{period.battle_end.astimezone(JST):%m/%d} まで）。"
                    "収集間隔を短くします。"
                )
        elif phase == PHASE_IDLE and previous in (PHASE_TRAINING, PHASE_BATTLE):
            await self._finish_period(period, now)

    async def _ensure_threads(self, period: Period) -> None:
        if self._threads_ready:
            return
        await self.poster.ensure_boss_threads(period.cb_period)
        self._threads_ready = True

    async def _announce_training(self, period: Period) -> None:
        from discord_bot.commands import bosses_embed

        embed = bosses_embed(self)
        embed.title = "収集を開始しました"
        embed.description = (
            f"トレーニング期間: {period.training_start.astimezone(JST):%m/%d %H:%M} 〜\n"
            f"クラバト本番: {period.battle_start.astimezone(JST):%m/%d} 〜 "
            f"{period.battle_end.astimezone(JST):%m/%d}"
        )
        await self.poster.send_notice(embed=embed)

    async def _finish_period(self, period: Period, now: datetime) -> None:
        """Flush the queue before stopping (11-4 decision: post everything)."""
        remaining = len(self.store.pending_videos(period.cb_period))
        if remaining:
            logger.info("flushing %d pending videos before going idle", remaining)
            await self.poster.post_pending(period.cb_period, now)

        if not self.store.mark_notified(period.cb_period, "end"):
            return
        counts = self.store.count_by_boss(period.cb_period)
        lines = [
            f"{boss.index}ボス {boss.name}: {counts.get(boss.index, 0)}件"
            for boss in self.bosses.bosses
        ]
        total = sum(counts.values())
        await self.poster.send_notice(
            f"**クラバト期間が終了しました**（合計 {total}件）\n" + "\n".join(lines)
        )
        self.poster.reset_daily_limit_notices()

    async def _maybe_remind(self, now: datetime) -> None:
        """Nudge the operator when /start was forgotten (11-1 decision)."""
        from schedule import offset_period

        local = now.astimezone(JST)
        offset = offset_period(local.year, local.month, self.config.schedule)
        if not should_remind(
            self.config.schedule,
            now,
            trigger_started=self._stored_trigger_start() is not None,
            already_reminded=self.store.is_notified(offset.cb_period, "reminder"),
        ):
            return

        self.store.ensure_period(offset)
        if not self.store.mark_notified(offset.cb_period, "reminder"):
            return
        await self.poster.send_notice(
            f"**クラバト期間（{offset.training_start.astimezone(JST):%m/%d} 開始予定）ですが、"
            "まだ収集が始まっていません。**\n"
            "`config/bosses.yaml` を今月のボス構成に更新してから `/start` を実行してください。"
        )

    def _month_matches(self) -> bool:
        """Guard against collecting with last month's bosses (docs/spec/04 §3)."""
        return self.bosses.month == datetime.now(JST).strftime("%Y-%m")

    async def _warn_stale_bosses(self, period: Period) -> None:
        logger.error(
            "bosses.yaml is stale; staying idle: bosses_month=%s current=%s",
            self.bosses.month,
            datetime.now(JST).strftime("%Y-%m"),
        )
        await self.poster.send_notice(
            f"⚠️ **ボス構成が未更新です。**`bosses.yaml` の月は `{self.bosses.month}` ですが、"
            f"現在は `{datetime.now(JST):%Y-%m}` です。\n"
            "前月のボス名で収集しないよう、収集を開始せずに待機します。"
            "`config/bosses.yaml` を更新して `/reload` を実行してください。"
        )


def _candidate_periods(now: datetime) -> list[str]:
    """This month plus the previous one — a period started late in the month
    can still be running past the month boundary."""
    year, month = now.year, now.month
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    return [f"{year:04d}-{month:02d}", f"{prev_year:04d}-{prev_month:02d}"]


def main() -> None:
    load_dotenv()
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN is not set (see .env.example)")

    config = load_config(CONFIG_PATH)
    bosses = load_bosses(BOSSES_PATH)
    store = Store(DB_PATH)

    current_month = datetime.now(JST).strftime("%Y-%m")
    if bosses.month != current_month:
        logger.warning(
            "bosses.yaml month does not match the current month: bosses=%s current=%s",
            bosses.month,
            current_month,
        )

    bot = CollectorBot(config, bosses, store, os.getenv("YOUTUBE_API_KEY"))
    try:
        bot.run(token, log_handler=None)
    finally:
        store.close()


if __name__ == "__main__":
    main()
