"""Serialized posting queue (docs/spec/08 §3).

Embed construction lives in interface.embeds; this module owns ordering,
rate-limit handling, the daily cap and thread management.
status becomes "posted" only after Discord confirms the message.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import discord

from priconne_cb_collector.adapters.sqlite_store import Store
from priconne_cb_collector.domain.models import BossesConfig
from priconne_cb_collector.domain.settings import LAYOUT_PER_BOSS_THREAD, AppConfig
from priconne_cb_collector.interface.embeds import build_video_embed

logger = logging.getLogger(__name__)

REASON_DAILY_LIMIT = "daily_limit"


class Poster:
    """Serializes posting so rate limits and the daily cap are respected."""

    def __init__(
        self,
        bot: discord.Client,
        config: AppConfig,
        bosses: BossesConfig,
        store: Store,
    ):
        self.bot = bot
        self.config = config
        self.bosses = bosses
        self.store = store
        self._lock = asyncio.Lock()
        self._limit_notified: set[tuple[str, int | None]] = set()

    async def ensure_boss_threads(self, cb_period: str) -> dict[int, int]:
        """Create the per-boss threads once per period; reuse them on restart."""
        if self.config.discord.layout != LAYOUT_PER_BOSS_THREAD:
            return {}

        existing = self.store.load_boss_threads(cb_period)
        channel = await self._get_channel()
        if channel is None:
            return existing

        thread_ids = dict(existing)
        for boss in self.bosses.bosses:
            if boss.index in thread_ids and await self._thread_exists(thread_ids[boss.index]):
                continue
            try:
                thread = await channel.create_thread(
                    name=f"{boss.index}ボス: {boss.name}",
                    type=discord.ChannelType.public_thread,
                )
                thread_ids[boss.index] = thread.id
                logger.info("created boss thread: boss=%d thread_id=%d", boss.index, thread.id)
            except Exception:
                logger.exception("failed to create boss thread: boss=%d", boss.index)

        if thread_ids != existing:
            self.store.save_boss_threads(cb_period, thread_ids)
        return thread_ids

    async def post_pending(self, cb_period: str, now: datetime | None = None) -> int:
        """Post every pending video for the period. Returns the count posted."""
        now = now or datetime.now(UTC)
        posted = 0
        async with self._lock:
            for row in self.store.pending_videos(cb_period):
                try:
                    if await self._post_one(row, cb_period, now):
                        posted += 1
                        await asyncio.sleep(self.config.discord.post_interval_seconds)
                except Exception:
                    logger.exception("failed to post video: video_id=%s", row["video_id"])
        return posted

    async def _post_one(self, row, cb_period: str, now: datetime) -> bool:
        boss_index = row["boss_index"]
        cap = self.config.discord.max_posts_per_boss_per_day
        if cap and self.store.count_posted_today(boss_index, now) >= cap:
            self.store.mark_filtered(row["video_id"], REASON_DAILY_LIMIT)
            await self._notify_daily_limit(cb_period, boss_index)
            return False

        target = await self._resolve_target(cb_period, row)
        if target is None:
            logger.warning("no target channel for video: video_id=%s", row["video_id"])
            return False

        embed = build_video_embed(row, self.bosses)
        message = await self._send_with_retry(target, embed)
        if message is None:
            return False

        # Only now, after Discord confirmed it (docs/spec/08 §3).
        self.store.mark_posted(row["video_id"], message.id, now)
        logger.info(
            "posted video: video_id=%s boss=%s channel_id=%s",
            row["video_id"],
            boss_index,
            getattr(target, "id", None),
        )
        return True

    async def _send_with_retry(self, target, embed, attempts: int = 3):
        for attempt in range(1, attempts + 1):
            try:
                return await target.send(embed=embed)
            except discord.HTTPException as exc:
                if exc.status == 429:
                    wait = float(getattr(exc, "retry_after", 0) or 5)
                    logger.warning("rate limited; waiting %.1fs (attempt %d)", wait, attempt)
                    await asyncio.sleep(wait)
                    continue
                logger.exception("discord send failed: status=%s", exc.status)
                return None
        return None

    async def _resolve_target(self, cb_period: str, row):
        channel = await self._get_channel()
        if self.config.discord.layout != LAYOUT_PER_BOSS_THREAD:
            return channel
        # Summary videos and unclassified ones go to the parent channel.
        if row["is_summary"] or not row["boss_index"]:
            return channel
        thread_ids = self.store.load_boss_threads(cb_period)
        thread_id = thread_ids.get(row["boss_index"])
        if thread_id is None:
            return channel
        return await self._fetch_channel(thread_id) or channel

    async def _notify_daily_limit(self, cb_period: str, boss_index: int | None) -> None:
        """Announce the cap once per boss per run (docs/spec/08 §3)."""
        key = (cb_period, boss_index)
        if key in self._limit_notified:
            return
        self._limit_notified.add(key)

        if boss_index:
            target = await self._resolve_target(
                cb_period, {"is_summary": 0, "boss_index": boss_index}
            )
        else:
            target = await self._get_channel()
        if target is None:
            return
        try:
            await target.send(
                f"本日の投稿上限（{self.config.discord.max_posts_per_boss_per_day}件）に達しました。"
                "以降の動画は明日以降に投稿されます。"
            )
        except Exception:
            logger.exception("failed to notify daily limit: boss=%s", boss_index)

    def reset_daily_limit_notices(self) -> None:
        self._limit_notified.clear()

    async def send_notice(self, content: str = "", embed: discord.Embed | None = None):
        channel = await self._get_channel()
        if channel is None:
            logger.error(
                "notice channel unavailable: channel_id=%s", self.config.discord.channel_id
            )
            return None
        try:
            return await channel.send(content=content or None, embed=embed)
        except Exception:
            logger.exception("failed to send notice")
            return None

    async def _get_channel(self):
        return await self._fetch_channel(self.config.discord.channel_id)

    async def _fetch_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.bot.fetch_channel(channel_id)
        except Exception:
            logger.exception("failed to fetch channel: channel_id=%s", channel_id)
            return None

    async def _thread_exists(self, thread_id: int) -> bool:
        return await self._fetch_channel(thread_id) is not None
