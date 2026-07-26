"""YouTube Data API v3 client with quota accounting (docs/spec/05 §2-4).

Quota costs: search.list = 100 units per call, videos.list = 1 unit per call
(up to 50 ids). Always batch through videos.list; it is nearly free.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime

import httpx

from priconne_cb_collector.domain.models import VideoMeta

logger = logging.getLogger(__name__)

API_BASE = "https://www.googleapis.com/youtube/v3"
SEARCH_COST = 100
VIDEOS_LIST_COST = 1
VIDEOS_LIST_BATCH = 50

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2.0

_ISO_DURATION = re.compile(r"^P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


class QuotaExceededError(Exception):
    """The API reported quotaExceeded. Never retried; search stops for the day."""


class YouTubeClient:
    def __init__(self, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def search_videos(
        self, query: str, published_after: datetime, max_results: int = 50
    ) -> tuple[list[VideoMeta], int]:
        """search.list, the only way videos are found. Returns (videos, units used).

        One call costs 100 units no matter how many results come back, so the
        caller passes every boss name in a single OR query (docs/spec/05 §1).
        """
        params = {
            "key": self._api_key,
            "part": "snippet",
            "type": "video",
            "order": "date",
            "maxResults": max_results,
            "regionCode": "JP",
            "relevanceLanguage": "ja",
            "publishedAfter": published_after.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "q": query,
        }
        data = await self._get("search", params)
        videos: list[VideoMeta] = []
        for item in data.get("items", []):
            try:
                snippet = item["snippet"]
                videos.append(
                    VideoMeta(
                        video_id=item["id"]["videoId"],
                        title=snippet["title"],
                        channel_id=snippet["channelId"],
                        published_at=_parse_rfc3339(snippet["publishedAt"]),
                        description=snippet.get("description", ""),
                        channel_title=snippet.get("channelTitle", ""),
                    )
                )
            except Exception:
                logger.exception("failed to parse search item: query=%r", query)
        logger.debug("api search: query=%r count=%d units=%d", query, len(videos), SEARCH_COST)
        return videos, SEARCH_COST

    async def enrich_videos(self, video_ids: list[str]) -> tuple[dict[str, dict], int]:
        """videos.list in batches of 50. Returns (details by id, units used)."""
        details: dict[str, dict] = {}
        units = 0
        for i in range(0, len(video_ids), VIDEOS_LIST_BATCH):
            batch = video_ids[i : i + VIDEOS_LIST_BATCH]
            params = {
                "key": self._api_key,
                "part": "snippet,contentDetails,statistics,liveStreamingDetails",
                "id": ",".join(batch),
            }
            data = await self._get("videos", params)
            units += VIDEOS_LIST_COST
            for item in data.get("items", []):
                details[item["id"]] = item
        logger.debug(
            "videos.list: requested=%d got=%d units=%d", len(video_ids), len(details), units
        )
        return details, units

    async def _get(self, endpoint: str, params: dict) -> dict:
        """GET with exponential backoff. quotaExceeded is never retried."""
        backoff = INITIAL_BACKOFF_SECONDS
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self._client.get(
                    f"{API_BASE}/{endpoint}", params=params, timeout=20.0
                )
                if response.status_code == 403 and _is_quota_exceeded(response):
                    raise QuotaExceededError(f"quotaExceeded on {endpoint}")
                response.raise_for_status()
                return response.json()
            except QuotaExceededError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt == MAX_RETRIES:
                    break
                logger.warning(
                    "youtube api error, retrying: endpoint=%s attempt=%d error=%s",
                    endpoint,
                    attempt,
                    exc,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
        raise RuntimeError(f"youtube api failed after {MAX_RETRIES} attempts: {last_error}")


def apply_details(video: VideoMeta, item: dict) -> VideoMeta:
    """Merge a videos.list item into a VideoMeta (description, duration, ...)."""
    snippet = item.get("snippet", {})
    content = item.get("contentDetails", {})
    stats = item.get("statistics", {})
    live = item.get("liveStreamingDetails")

    video.description = snippet.get("description", video.description)
    video.channel_title = snippet.get("channelTitle", video.channel_title)
    video.channel_id = snippet.get("channelId", video.channel_id)
    if snippet.get("publishedAt"):
        video.published_at = _parse_rfc3339(snippet["publishedAt"])
    video.duration_sec = parse_duration(content.get("duration"))
    view_count = stats.get("viewCount")
    video.view_count = int(view_count) if view_count is not None else None
    video.is_live = _is_live(item, live)
    return video


def parse_duration(iso_duration: str | None) -> int | None:
    """ISO 8601 duration to seconds. Returns None when unparseable."""
    if not iso_duration:
        return None
    match = _ISO_DURATION.match(iso_duration)
    if not match:
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _is_live(item: dict, live: dict | None) -> bool:
    """Live now or scheduled. A finished archive has actualEndTime and is fine."""
    if item.get("snippet", {}).get("liveBroadcastContent") in ("live", "upcoming"):
        return True
    return bool(live and "actualEndTime" not in live)


def _is_quota_exceeded(response: httpx.Response) -> bool:
    try:
        errors = response.json().get("error", {}).get("errors", [])
    except Exception:
        return False
    return any(e.get("reason") == "quotaExceeded" for e in errors)


def _parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
