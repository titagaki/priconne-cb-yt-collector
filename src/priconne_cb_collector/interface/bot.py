"""The Discord client: polling loop and phase-transition announcements.

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
from priconne_cb_collector.domain.models import (
    PHASE_BATTLE,
    PHASE_IDLE,
    PHASE_TRAINING,
    BossesConfig,
    Period,
)
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
            logger.warning("YOUTUBE_API_KEY is not set; running with rss only")

        self.periods = PeriodService(config, store)
        self.collector = Collector(config, bosses, store, self.http_client, youtube)
        self.poster = Poster(self, config, bosses, store)

        self._last_rss: datetime | None = None
        self._last_api: datetime | None = None
        self._last_phase: str | None = None
        self._threads_ready = False

    # ---- period delegation (used by the slash commands) ----

    def current_period(self) -> Period | None:
        return self.periods.current_period()

    def current_phase(self, now: datetime | None = None) -> str:
        return self.periods.current_phase(now)

    async def start_period(self, now: datetime) -> Period:
        period = self.periods.start(now)
        self._apply_config(self.periods.config)
        self._last_phase = None  # let the next tick emit the training announcement
        self._threads_ready = False
        return period

    def stop_period(self) -> bool:
        if self.periods.stop() is None:
            return False
        self._last_phase = PHASE_IDLE
        self._threads_ready = False
        return True

    def set_manual_period(self, training_start, battle_start, end) -> Period:
        period = self.periods.override(training_start, battle_start, end)
        self._apply_config(self.periods.config)
        self._last_phase = None
        self._threads_ready = False
        return period

    def reload_config(self) -> None:
        self._apply_config(load_config(self.paths.config))
        self.bosses = load_bosses(self.paths.bosses)
        self.collector.bosses = self.bosses
        self.poster.bosses = self.bosses
        logger.info("config reloaded: bosses_month=%s", self.bosses.month)

    def _apply_config(self, config: AppConfig) -> None:
        """Propagate a config change to every component holding a copy."""
        self.config = config
        self.periods.config = config
        self.collector.config = config
        self.poster.config = config

    def bosses_embed(self) -> discord.Embed:
        return build_bosses_embed(self.bosses, datetime.now(JST).strftime("%Y-%m"))

    async def run_collection(self, *, run_api_search: bool = False):
        """One collection round on demand (/collect). Posts what it finds."""
        now = datetime.now(UTC)
        period = self.periods.current_period(now)
        if period is None:
            raise RuntimeError("稼働期間が未設定です")
        result = await self.collector.collect(period, now=now, run_api_search=run_api_search)
        self._last_rss = now
        if run_api_search and not result.api_search_skipped:
            self._last_api = now
        await self.poster.post_pending(period.cb_period, now)
        return result

    # ---- lifecycle ----

    async def setup_hook(self) -> None:
        from priconne_cb_collector.interface.commands import setup_commands

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
        now = datetime.now(UTC)
        period = self.periods.current_period(now)
        phase = self.periods.current_phase(now)

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
            return  # the stale-bosses warning was already posted on transition

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

        rss_due = self._is_due(self._last_rss, now, rss_minutes * 60)
        api_due = self._is_due(self._last_api, now, api_hours * 3600)
        if not rss_due and not api_due:
            return

        result = await self.collector.collect(period, now=now, run_api_search=api_due)
        self._last_rss = now
        if api_due and not result.api_search_skipped:
            self._last_api = now

    @staticmethod
    def _is_due(last: datetime | None, now: datetime, interval_seconds: float) -> bool:
        return last is None or (now - last).total_seconds() >= interval_seconds

    async def _handle_transition(
        self, previous: str | None, phase: str, period: Period, now: datetime
    ) -> None:
        if phase in (PHASE_TRAINING, PHASE_BATTLE) and not self._month_matches():
            await self._warn_stale_bosses()
            return

        if phase == PHASE_TRAINING:
            if self.periods.claim_notice(period.cb_period, "training"):
                await self._announce_training(period)
            await self._ensure_threads(period)
        elif phase == PHASE_BATTLE:
            await self._ensure_threads(period)
            if self.periods.claim_notice(period.cb_period, "battle"):
                await self.poster.send_notice(
                    f"**クラバト本番が始まりました**"
                    f"（{period.battle_end.astimezone(JST):%m/%d} まで）。"
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
        embed = self.bosses_embed()
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

        if not self.periods.claim_notice(period.cb_period, "end"):
            return
        counts = self.store.count_by_boss(period.cb_period)
        lines = [
            f"{boss.index}ボス {boss.name}: {counts.get(boss.index, 0)}件"
            for boss in self.bosses.bosses
        ]
        await self.poster.send_notice(
            f"**クラバト期間が終了しました**（合計 {sum(counts.values())}件）\n" + "\n".join(lines)
        )
        self.poster.reset_daily_limit_notices()

    async def _maybe_remind(self, now: datetime) -> None:
        """Nudge the operator when /start was forgotten (11-1 decision)."""
        offset = self.periods.pending_reminder(now)
        if offset is None:
            return
        await self.poster.send_notice(
            f"**クラバト期間（{offset.training_start.astimezone(JST):%m/%d} 開始予定）ですが、"
            "まだ収集が始まっていません。**\n"
            "`config/bosses.yaml` を今月のボス構成に更新してから `/start` を実行してください。"
        )

    def _month_matches(self) -> bool:
        """Guard against collecting with last month's bosses (docs/spec/04 §3)."""
        return self.bosses.month == datetime.now(JST).strftime("%Y-%m")

    async def _warn_stale_bosses(self) -> None:
        current = datetime.now(JST).strftime("%Y-%m")
        logger.error(
            "bosses.yaml is stale; staying idle: bosses_month=%s current=%s",
            self.bosses.month,
            current,
        )
        await self.poster.send_notice(
            f"⚠️ **ボス構成が未更新です。**`bosses.yaml` の月は `{self.bosses.month}` ですが、"
            f"現在は `{current}` です。\n"
            "前月のボス名で収集しないよう、収集を開始せずに待機します。"
            "`config/bosses.yaml` を更新して `/reload` を実行してください。"
        )
