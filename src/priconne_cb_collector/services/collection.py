"""Collection pipeline: fetch -> enrich -> classify -> filter -> store.

Spec: docs/spec/05, 06 §5, 10 §1. A failure on one video is recorded as
status="error" and never aborts the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

from priconne_cb_collector.adapters import youtube_rss as rss
from priconne_cb_collector.adapters.sqlite_store import STATUS_FILTERED, STATUS_PENDING, Store
from priconne_cb_collector.adapters.youtube_api import (
    SEARCH_COST,
    QuotaExceededError,
    YouTubeClient,
    apply_details,
)
from priconne_cb_collector.domain.classify import classify_video
from priconne_cb_collector.domain.models import BossesConfig, Period, VideoMeta
from priconne_cb_collector.domain.schedule import JST
from priconne_cb_collector.domain.settings import ON_UNKNOWN_SKIP, AppConfig

logger = logging.getLogger(__name__)

REASON_TOO_SHORT = "too_short"
REASON_TOO_LONG = "too_long"
REASON_LIVE = "live"
REASON_NG_WORD = "ng_word"
REASON_BOSS_UNKNOWN = "boss_unknown"


@dataclass
class CollectResult:
    fetched: int = 0
    new: int = 0
    pending: int = 0
    filtered: int = 0
    errors: int = 0
    quota_used: int = 0
    api_search_skipped: bool = False
    filter_reasons: dict[str, int] = field(default_factory=dict)


class Collector:
    def __init__(
        self,
        config: AppConfig,
        bosses: BossesConfig,
        store: Store,
        http: httpx.AsyncClient,
        youtube: YouTubeClient | None = None,
    ):
        self.config = config
        self.bosses = bosses
        self.store = store
        self.http = http
        self.youtube = youtube

    async def collect(
        self,
        period: Period,
        *,
        now: datetime | None = None,
        run_api_search: bool = False,
    ) -> CollectResult:
        now = now or datetime.now(UTC)
        result = CollectResult()

        candidates: dict[str, VideoMeta] = {}
        for video in await self._fetch_rss(now):
            candidates.setdefault(video.video_id, video)

        if run_api_search:
            searched, skipped = await self._fetch_api_search(period, now, result)
            result.api_search_skipped = skipped
            for video in searched:
                candidates.setdefault(video.video_id, video)

        result.fetched = len(candidates)

        # Skip anything already stored before spending quota enriching it.
        known = self.store.known_video_ids(list(candidates))
        fresh = {vid: v for vid, v in candidates.items() if vid not in known}
        result.new = len(fresh)
        if not fresh:
            logger.info("collect done: fetched=%d new=0", result.fetched)
            # An API search round can spend quota even when it finds nothing new.
            self._log_daily_quota(now, result)
            return result

        await self._enrich(fresh, result)

        for video in fresh.values():
            try:
                self._process(video, period, now, result)
            except Exception as exc:
                result.errors += 1
                logger.exception("failed to process video: video_id=%s", video.video_id)
                self._store_error(video, period, str(exc))

        logger.info(
            "collect done: fetched=%d new=%d pending=%d filtered=%d errors=%d quota=%d",
            result.fetched,
            result.new,
            result.pending,
            result.filtered,
            result.errors,
            result.quota_used,
        )
        self._log_daily_quota(now, result)
        return result

    def _log_daily_quota(self, now: datetime, result: CollectResult) -> None:
        """Daily running total at INFO (docs/spec/10 §2).

        Per-call consumption is logged at DEBUG by the API client; this is the
        line an operator greps to see how much of the day's budget is gone.
        """
        if not result.quota_used:
            return
        logger.info(
            "quota daily total: date=%s used=%d limit=%d",
            now.astimezone(JST).date().isoformat(),
            self.store.quota_used(now),
            self.config.youtube.quota_limit_per_day,
        )

    # ---- fetching ----

    async def _fetch_rss(self, now: datetime) -> list[VideoMeta]:
        videos: list[VideoMeta] = []
        for channel in self.config.youtube.channels:
            try:
                etag, last_fetch = self.store.get_etag(channel.id)
                fetched, new_etag, not_modified = await rss.fetch_channel(
                    self.http, channel, etag, last_fetch
                )
                self.store.save_etag(channel.id, new_etag, now)
                if not not_modified:
                    videos.extend(fetched)
            except Exception:
                logger.exception("rss fetch failed: channel_id=%s", channel.id)
        return videos

    async def _fetch_api_search(
        self, period: Period, now: datetime, result: CollectResult
    ) -> tuple[list[VideoMeta], bool]:
        """Run one search round (5 bosses). Degrades to RSS-only on quota limits."""
        if self.youtube is None:
            return [], True

        planned = SEARCH_COST * len(self.bosses.bosses)
        used = self.store.quota_used(now)
        limit = self.config.youtube.quota_limit_per_day
        if used + planned > limit:
            logger.warning(
                "api search skipped to stay within quota: used=%d planned=%d limit=%d",
                used,
                planned,
                limit,
            )
            return [], True

        published_after = period.start - timedelta(days=self.config.youtube.search_lookback_days)
        videos: list[VideoMeta] = []
        for boss in self.bosses.bosses:
            # Boss name alone. Adding "プリコネ"/"クラバト" would drop the many
            # videos whose titles carry neither (docs/spec/05 §2).
            query = boss.name
            try:
                found, units = await self.youtube.search_videos(query, published_after)
            except QuotaExceededError:
                logger.warning("quotaExceeded; degrading to rss-only for today")
                self.store.add_quota(limit, now)  # block further searches today
                return videos, True
            except Exception:
                logger.exception("api search failed: query=%r", query)
                continue
            self.store.add_quota(units, now)
            result.quota_used += units
            videos.extend(found)
        return videos, False

    async def _enrich(self, fresh: dict[str, VideoMeta], result: CollectResult) -> None:
        """videos.list gives description / duration / live state (1 unit per 50)."""
        if self.youtube is None:
            return
        try:
            details, units = await self.youtube.enrich_videos(list(fresh))
        except QuotaExceededError:
            logger.warning("quotaExceeded during videos.list; skipping enrichment")
            return
        except Exception:
            logger.exception("videos.list failed; classifying with rss metadata only")
            return
        self.store.add_quota(units)
        result.quota_used += units
        for video_id, item in details.items():
            if video_id in fresh:
                apply_details(fresh[video_id], item)

    # ---- per-video processing ----

    def _process(
        self,
        video: VideoMeta,
        period: Period,
        now: datetime,
        result: CollectResult,
    ) -> None:
        published_in_period = video.published_at >= period.start
        classification = classify_video(
            video.title,
            video.description,
            self.bosses.bosses,
            enable_ex_notation=self.config.classify.enable_ex_notation,
            published_in_period=published_in_period,
        )

        reason = self._filter_reason(video, classification)
        status = STATUS_FILTERED if reason else STATUS_PENDING

        inserted = self.store.add_video(
            video,
            classification,
            cb_period=period.cb_period,
            status=status,
            filter_reason=reason,
            discovered_at=now,
        )
        if not inserted:
            return

        if reason:
            result.filtered += 1
            result.filter_reasons[reason] = result.filter_reasons.get(reason, 0) + 1
        else:
            result.pending += 1

        # Spec 10 §2: the matched strings are required for tuning the classifier.
        logger.info(
            "video classified: video_id=%s via=%s boss=%s source=%s matched=%s "
            "battle_type=%s postable=%s reason=%s title=%r",
            video.video_id,
            video.discovered_via,
            classification.boss.indices,
            classification.boss.match_source,
            classification.boss.matched_strings,
            classification.battle_type,
            reason is None,
            reason,
            video.title,
        )

    def _filter_reason(self, video: VideoMeta, classification) -> str | None:
        """Exclusion filters (docs/spec/06 §5). Videos are stored either way."""
        exclude = self.config.youtube.exclude
        if exclude.exclude_live and video.is_live:
            return REASON_LIVE
        if video.duration_sec is not None:
            if video.duration_sec < exclude.min_duration_seconds:
                return REASON_TOO_SHORT
            if video.duration_sec > exclude.max_duration_seconds:
                return REASON_TOO_LONG
        if any(word in video.title for word in exclude.title_ng_words):
            return REASON_NG_WORD
        # Unclassified videos are posted by default: missing one costs more than
        # an off-topic post (docs/spec/01 §2).
        skip_unknown = self.config.classify.on_boss_unknown == ON_UNKNOWN_SKIP
        if skip_unknown and not classification.boss.indices:
            return REASON_BOSS_UNKNOWN
        return None

    def _store_error(self, video: VideoMeta, period: Period, message: str) -> None:
        from priconne_cb_collector.domain.models import Classification

        try:
            inserted = self.store.add_video(
                video,
                Classification(),
                cb_period=period.cb_period,
                status="error",
                filter_reason=message[:200],
            )
            if not inserted:
                self.store.mark_error(video.video_id, message[:200])
        except Exception:
            logger.exception("failed to record error row: video_id=%s", video.video_id)
