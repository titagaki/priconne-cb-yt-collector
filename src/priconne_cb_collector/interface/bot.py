"""The Discord client: polling loop and start/end announcements.

Spec: docs/spec/04. Period arithmetic lives in services.lifecycle; this class
owns only the Discord-facing side effects and the loop cadence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import discord
import httpx
from discord.ext import tasks

from priconne_cb_collector.adapters.config_file import load_bosses, load_config
from priconne_cb_collector.adapters.sqlite_store import Store
from priconne_cb_collector.adapters.youtube_api import YouTubeClient
from priconne_cb_collector.domain.models import BossesConfig, Period
from priconne_cb_collector.domain.schedule import JST
from priconne_cb_collector.domain.settings import AppConfig
from priconne_cb_collector.interface.embeds import build_bosses_embed
from priconne_cb_collector.interface.poster import Poster
from priconne_cb_collector.services.collection import Collector
from priconne_cb_collector.services.lifecycle import PeriodService

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
USER_AGENT = "priconne-cb-yt-collector/0.1"


@dataclass(frozen=True)
class Paths:
    """Where the bot reads its configuration and writes its database."""

    config: Path = Path("config/config.yaml")
    bosses: Path = Path("config/bosses.yaml")
    database: Path = Path("data/bot.db")


class CollectorBot(discord.Client):
    def __init__(
        self,
        config: AppConfig,
        bosses: BossesConfig,
        store: Store,
        api_key: str | None = None,
        paths: Paths | None = None,
    ):
        super().__init__(intents=discord.Intents.default())
        self.tree = discord.app_commands.CommandTree(self)
        self.config = config
        self.bosses = bosses
        self.store = store
        self.paths = paths or Paths()

        self.http_client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT})
        youtube = YouTubeClient(self.http_client, api_key) if api_key else None
        if youtube is None:
            logger.error("YOUTUBE_API_KEY is not set; nothing can be collected")

        self.periods = PeriodService(store)
        self.collector = Collector(config, bosses, store, youtube)
        self.poster = Poster(self, config, bosses, store)

        self._last_search: datetime | None = None
        self._was_collecting: bool | None = None
        self._threads_ready = False

    # ---- period delegation (used by the slash commands) ----

    def current_period(self) -> Period | None:
        return self.periods.current_period()

    def is_collecting(self, now: datetime | None = None) -> bool:
        return self.periods.is_collecting(now)

    async def start_period(self, now: datetime) -> Period:
        """/start: open a period and wake the loop up (docs/spec/04 §2)."""
        period = self.periods.start(now)
        self._was_collecting = None  # let the next tick emit the start announcement
        self._threads_ready = False
        self._last_search = None  # collect on the first tick, not one interval later
        self._resume_loop()
        return period

    async def stop_period(self) -> bool:
        """/stop: close the period, post the summary, and park the loop."""
        now = datetime.now(UTC)
        period = self.periods.stop(now)
        if period is None:
            return False
        self._was_collecting = False
        self._threads_ready = False
        self._park_loop()
        await self._finish_period(period, now)
        return True

    def reload_config(self) -> None:
        self._apply_config(load_config(self.paths.config))
        self.bosses = load_bosses(self.paths.bosses)
        self.collector.bosses = self.bosses
        self.poster.bosses = self.bosses
        logger.info("config reloaded: bosses_month=%s", self.bosses.month)

    def _apply_config(self, config: AppConfig) -> None:
        """Propagate a config change to every component holding a copy."""
        self.config = config
        self.collector.config = config
        self.poster.config = config

    def bosses_embed(self) -> discord.Embed:
        return build_bosses_embed(self.bosses, datetime.now(JST).strftime("%Y-%m"))

    async def run_collection(self):
        """One collection round on demand (/collect). Posts what it finds.

        Refused while not collecting: a video collected then belongs to no
        cb_period, which is a NOT NULL column (docs/spec/07 §1).
        """
        now = datetime.now(UTC)
        period = self.periods.current_period(now)
        if period is None or not self.periods.is_collecting(now):
            raise RuntimeError("収集期間外です")
        result = await self.collector.collect(period, now=now)
        self._last_search = now
        await self.poster.post_pending(period.cb_period, now)
        return result

    # ---- lifecycle ----

    async def setup_hook(self) -> None:
        from priconne_cb_collector.interface.commands import setup_commands

        setup_commands(self)
        await self.tree.sync()
        if self.periods.current_period() is not None:
            self._resume_loop()  # resume a period that was open before the restart

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

    def _resume_loop(self) -> None:
        """Run the loop again from now. There is no idle cadence: while stopped
        the loop does not run at all (docs/spec/04 §3)."""
        if self.tick.is_running():
            self.tick.restart()
        else:
            self.tick.start()

    def _park_loop(self) -> None:
        if self.tick.is_running():
            self.tick.cancel()

    async def _tick_once(self) -> None:
        """The loop only runs while a period is open, so every tick collects."""
        now = datetime.now(UTC)
        period = self.periods.current_period(now)

        if period is None:
            self._park_loop()  # /stop already posted the summary
            return

        self.store.ensure_period(period)

        if self._was_collecting is not True:
            await self._begin_period(period)
            self._was_collecting = True

        if not self._month_matches(period):
            return  # the stale-bosses warning was already posted on the transition

        await self._run_due_collections(period, now)
        await self.poster.post_pending(period.cb_period, now)

    async def _run_due_collections(self, period: Period, now: datetime) -> None:
        interval = self.config.polling.search_interval_minutes * 60
        if not self._is_due(self._last_search, now, interval):
            return

        # Recorded even when the search is skipped for quota, so an exhausted
        # budget retries on the normal cadence instead of on every tick.
        self._last_search = now
        await self.collector.collect(period, now=now)

    @staticmethod
    def _is_due(last: datetime | None, now: datetime, interval_seconds: float) -> bool:
        return last is None or (now - last).total_seconds() >= interval_seconds

    async def _begin_period(self, period: Period) -> None:
        """First tick of an open period: announce it and prepare the threads."""
        if not self._month_matches(period):
            await self._warn_stale_bosses(period)
            return
        if self.periods.claim_notice(period.cb_period, "start"):
            await self._announce_start(period)
        await self._ensure_threads(period)

    async def _ensure_threads(self, period: Period) -> None:
        if self._threads_ready:
            return
        await self.poster.ensure_boss_threads(period.cb_period)
        self._threads_ready = True

    async def _announce_start(self, period: Period) -> None:
        embed = self.bosses_embed()
        embed.title = "収集を開始しました"
        embed.description = (
            f"収集開始: {period.start.astimezone(JST):%m/%d %H:%M}\n"
            "`/stop` を実行するまで収集を続けます。"
        )
        await self.poster.send_notice(embed=embed)

    async def _finish_period(self, period: Period, now: datetime) -> None:
        """Flush the queue before stopping (11-4 decision: post everything).

        Reached only from /stop, which is the only way a period ends.
        """
        remaining = len(self.store.pending_videos(period.cb_period))
        if remaining:
            logger.info("flushing %d pending videos before going idle", remaining)
            await self.poster.post_pending(period.cb_period, now)

        if not self.periods.claim_notice(period.cb_period, "end"):
            return
        counts = self.store.count_by_boss(period.cb_period)
        lines = [
            f"{boss.index}ボス {boss.name}: {counts.get(boss.index, 0)}件"
            for boss in self.bosses.bosses
        ]
        await self.poster.send_notice(
            f"**収集を終了しました**（合計 {sum(counts.values())}件）\n" + "\n".join(lines)
        )
        self.poster.reset_daily_limit_notices()

    def _month_matches(self, period: Period) -> bool:
        """Guard against collecting with last month's bosses (docs/spec/04 §3).

        Compared against the period's key, not the wall clock: a run started on
        the 29th keeps collecting under its own month after midnight on the 1st.
        """
        return self.bosses.month == period.cb_period

    async def _warn_stale_bosses(self, period: Period) -> None:
        logger.error(
            "bosses.yaml is stale; staying idle: bosses_month=%s cb_period=%s",
            self.bosses.month,
            period.cb_period,
        )
        await self.poster.send_notice(
            f"⚠️ **ボス構成が未更新です。**`bosses.yaml` の月は `{self.bosses.month}` ですが、"
            f"収集対象は `{period.cb_period}` です。\n"
            "前月のボス名で収集しないよう、収集を開始せずに待機します。"
            "`config/bosses.yaml` を更新して `/reload` を実行してください。"
        )
