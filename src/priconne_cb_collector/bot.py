"""常駐 Bot: ポーリングループ、投稿、スラッシュコマンド。

The whole cycle is: search -> drop the ones already posted -> drop NG words ->
post to the boss's channel -> record it. There is no queue and no per-video
state; a video that fails to post is simply found again next round.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import discord
import httpx
from discord import app_commands
from discord.ext import tasks

from priconne_cb_collector.classify import is_ng, match_boss
from priconne_cb_collector.config import BossesConfig, Config
from priconne_cb_collector.store import JST, Period, Store
from priconne_cb_collector.youtube import YouTubeClient

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
DEFAULT_RETRY_AFTER = 5.0  # used only when Discord sends no Retry-After


@dataclass(frozen=True)
class Paths:
    config: Path
    bosses: Path
    database: Path


class CollectorBot(discord.Client):
    def __init__(
        self,
        config: Config,
        bosses: BossesConfig,
        store: Store,
        api_key: str,
        paths: Paths,
    ):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.config = config
        self.bosses = bosses
        self.store = store
        self.paths = paths
        self.http_client = httpx.AsyncClient(headers={"User-Agent": "priconne-cb-collector"})
        self.youtube = YouTubeClient(self.http_client, api_key)
        self._last_search: datetime | None = None

    # ---- lifecycle ----

    async def setup_hook(self) -> None:
        setup_commands(self)
        await self.tree.sync()
        if self.store.current_period() is not None:
            self._resume_loop()  # a period was open before the restart

    async def on_ready(self) -> None:
        logger.info("logged in: user=%s", self.user)

    async def close(self) -> None:
        await self.http_client.aclose()
        await super().close()

    def start_period(self, now: datetime) -> Period:
        period = self.store.open_period(now)
        self._last_search = None  # collect on the first tick, not one interval later
        self._resume_loop()
        logger.info("period started: cb_period=%s", period.cb_period)
        return period

    async def stop_period(self) -> Period | None:
        period = self.store.current_period()
        if period is None:
            return None
        self.store.close_period(period.cb_period)
        self._park_loop()
        logger.info("period stopped: cb_period=%s", period.cb_period)
        return period

    # ---- polling loop ----

    @tasks.loop(seconds=TICK_SECONDS)
    async def tick(self) -> None:
        try:
            await self.run_once()
        except Exception:
            logger.exception("tick failed")

    @tick.before_loop
    async def before_tick(self) -> None:
        await self.wait_until_ready()

    def _resume_loop(self) -> None:
        if self.tick.is_running():
            self.tick.restart()
        else:
            self.tick.start()

    def _park_loop(self) -> None:
        if self.tick.is_running():
            self.tick.cancel()

    async def run_once(self, now: datetime | None = None) -> int:
        """One cycle. Returns how many videos were posted."""
        now = now or datetime.now(UTC)
        period = self.store.current_period()
        if period is None:
            self._park_loop()
            return 0
        if self.bosses.month != period.cb_period:
            logger.warning(
                "bosses.yaml month does not match the period; not collecting: bosses=%s period=%s",
                self.bosses.month,
                period.cb_period,
            )
            return 0

        interval = self.config.search_interval_minutes * 60
        if self._last_search is not None and (now - self._last_search).total_seconds() < interval:
            return 0
        self._last_search = now

        return await self.collect(period, now)

    async def collect(self, period: Period, now: datetime | None = None) -> int:
        """Search, then post everything new. One video's failure never aborts."""
        now = now or datetime.now(UTC)
        published_after = period.start - timedelta(days=self.config.search_lookback_days)
        query = " OR ".join(boss.name for boss in self.bosses.bosses)
        try:
            found = await self.youtube.search(query, published_after)
        except Exception:
            logger.exception("search failed: query=%r", query)
            return 0

        candidates = {v.video_id: v for v in found}
        known = self.store.known_video_ids(list(candidates))
        posted = 0
        for video in candidates.values():
            if video.video_id in known:
                continue
            if is_ng(video.title, self.config.title_ng_words):
                logger.info("skipped by ng word: video_id=%s title=%r", video.video_id, video.title)
                continue
            try:
                if await self._post(video, period, now):
                    posted += 1
                    await asyncio.sleep(self.config.post_interval_seconds)
            except Exception:
                logger.exception("failed to post video: video_id=%s", video.video_id)

        logger.info("collect done: found=%d posted=%d", len(candidates), posted)
        return posted

    # ---- posting ----

    async def _post(self, video, period: Period, now: datetime) -> bool:
        boss_index = match_boss(video.title, self.bosses.bosses)
        channel = await self._fetch_channel(self.config.channel_for(boss_index))
        if channel is None:
            return False

        # The bare URL is enough: Discord expands it into a card by itself.
        message = await self._send_with_retry(channel, f"{video.title}\n{video.url}")
        if message is None:
            return False

        # Only now, after Discord confirmed it.
        self.store.mark_posted(video.video_id, video.title, boss_index, period.cb_period, now)
        logger.info(
            "posted video: video_id=%s boss=%s channel_id=%s title=%r",
            video.video_id,
            boss_index,
            channel.id,
            video.title,
        )
        return True

    async def _send_with_retry(self, channel, content: str, attempts: int = 3):
        for attempt in range(1, attempts + 1):
            try:
                return await channel.send(content)
            except discord.HTTPException as exc:
                if exc.status == 429:
                    # retry_after may legitimately be 0; only a missing value falls back.
                    retry_after = getattr(exc, "retry_after", None)
                    wait = float(retry_after) if retry_after is not None else DEFAULT_RETRY_AFTER
                    logger.warning("rate limited; waiting %.1fs (attempt %d)", wait, attempt)
                    await asyncio.sleep(wait)
                    continue
                logger.exception("discord send failed: status=%s", exc.status)
                return None
        return None

    async def _fetch_channel(self, channel_id: int):
        channel = self.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.fetch_channel(channel_id)
        except Exception:
            logger.exception("failed to fetch channel: channel_id=%s", channel_id)
            return None

    # ---- shared text ----

    def boss_roster(self) -> str:
        lines = [f"**対象月: {self.bosses.month}**"]
        lines += [
            f"{b.index}ボス {b.name}（別名: {'、'.join(b.aliases)}）" for b in self.bosses.bosses
        ]
        return "\n".join(lines)


class ConfirmView(discord.ui.View):
    """/start の確認ボタン。押した本人以外は操作できない。"""

    def __init__(self, user_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.confirmed = False

    @discord.ui.button(label="開始する", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("実行者のみ操作できます。", ephemeral=True)
            return
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("実行者のみ操作できます。", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()


def setup_commands(bot: CollectorBot) -> None:
    tree = bot.tree

    @tree.command(name="start", description="[管理者] 収集を開始します")
    @app_commands.default_permissions(administrator=True)
    async def start(interaction: discord.Interaction):
        if bot.store.current_period() is not None:
            await interaction.response.send_message("すでに収集中です。", ephemeral=True)
            return

        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(
            f"{bot.boss_roster()}\n\n"
            "**この構成で収集を開始します。**毎月ボスは入れ替わります。内容を確認してください。",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            await interaction.followup.send("開始をキャンセルしました。", ephemeral=True)
            return

        period = bot.start_period(datetime.now(UTC))
        # The only start announcement: the roster is already in the message above.
        await interaction.followup.send(
            f"**収集を開始しました**（対象期間 {period.cb_period}）\n"
            f"収集開始: {period.start.astimezone(JST):%m/%d %H:%M}\n"
            "`/stop` を実行するまで収集を続けます。"
        )

    @tree.command(name="stop", description="[管理者] 収集を停止します")
    @app_commands.default_permissions(administrator=True)
    async def stop(interaction: discord.Interaction):
        await interaction.response.defer()
        period = await bot.stop_period()
        if period is None:
            await interaction.followup.send("現在収集していません。", ephemeral=True)
            return
        counts = bot.store.count_by_boss(period.cb_period)
        lines = [f"{b.index}ボス {b.name}: {counts.get(b.index, 0)}件" for b in bot.bosses.bosses]
        lines.append(f"判定できず: {counts.get(None, 0)}件")
        await interaction.followup.send(
            f"**収集を終了しました**（合計 {sum(counts.values())}件）\n" + "\n".join(lines)
        )

    @tree.command(name="status", description="収集中かどうかと投稿件数を表示します")
    async def status(interaction: discord.Interaction):
        period = bot.store.current_period()
        if period is None:
            await interaction.response.send_message(
                "待機中です。`/start` で収集を開始してください。", ephemeral=True
            )
            return
        counts = bot.store.count_by_boss(period.cb_period)
        elapsed = int((datetime.now(UTC) - period.start).total_seconds() // 3600)
        await interaction.response.send_message(
            f"**収集中**（対象期間 {period.cb_period}）\n"
            f"開始: {period.start.astimezone(JST):%m/%d %H:%M}（{elapsed}時間経過）\n"
            f"投稿済み: {sum(counts.values())}件"
        )
