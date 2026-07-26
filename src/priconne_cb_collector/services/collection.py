"""Collection pipeline: fetch -> enrich -> classify -> filter -> store.

Spec: docs/spec/05, 06 §5, 10 §1. A failure on one video is recorded as
status="error" and never aborts the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

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
    search_skipped: bool = False
    filter_reasons: dict[str, int] = field(default_factory=dict)


class Collector:
    def __init__(
        self,
        config: AppConfig,
        bosses: BossesConfig,
        store: Store,
        youtube: YouTubeClient | None = None,
    ):
        self.config = config
        self.bosses = bosses
        self.store = store
        self.youtube = youtube

    async def collect(self, period: Period, *, now: datetime | None = None) -> CollectResult:
        now = now or datetime.now(UTC)
        result = CollectResult()

        searched, skipped = await self._search(period, now, result)
        result.search_skipped = skipped
        candidates: dict[str, VideoMeta] = {}
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

    def search_query(self) -> str:
        """Every boss name in one OR query.

        search.list costs 100 units per call regardless of the result count, so
        one combined call costs a fifth of one call per boss and lets the loop
        run every 30 minutes instead of every 90 (docs/spec/05 §1).

        Boss names only: adding "プリコネ"/"クラバト" would drop the many videos
        whose titles carry neither. Aliases are for classification, not search.
        """
        return " OR ".join(boss.name for boss in self.bosses.bosses)

    async def _search(
        self, period: Period, now: datetime, result: CollectResult
    ) -> tuple[list[VideoMeta], bool]:
        """One search round. Returns (videos, skipped)."""
        if self.youtube is None:
            return [], True

        used = self.store.quota_used(now)
        limit = self.config.youtube.quota_limit_per_day
        if used + SEARCH_COST > limit:
            logger.warning(
                "search skipped to stay within quota: used=%d planned=%d limit=%d",
                used,
                SEARCH_COST,
                limit,
            )
            return [], True

        published_after = period.start - timedelta(days=self.config.youtube.search_lookback_days)
        query = self.search_query()
        try:
            found, units = await self.youtube.search_videos(query, published_after)
        except QuotaExceededError:
            logger.warning("quotaExceeded; no more searches today")
            self.store.add_quota(limit, now)  # block further searches today
            return [], True
        except Exception:
            logger.exception("search failed: query=%r", query)
            return [], False
        self.store.add_quota(units, now)
        result.quota_used += units
        return found, False

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
            logger.exception("videos.list failed; classifying with search metadata only")
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
            "video classified: video_id=%s boss=%s source=%s matched=%s "
            "battle_type=%s postable=%s reason=%s title=%r",
            video.video_id,
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
