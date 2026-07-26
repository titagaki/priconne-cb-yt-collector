"""YouTube Data API v3: search.list only.

One search costs 100 units regardless of the result count, so every boss name
goes into a single OR query. At the default 30 minute cadence that is
48 x 100 = 4,800 units a day, well inside the 10,000 daily budget -- which is
why there is no quota bookkeeping here.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://www.googleapis.com/youtube/v3"
SEARCH_COST = 100
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2.0


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    published_at: datetime  # aware UTC
    channel_title: str = ""

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


class YouTubeClient:
    def __init__(self, client: httpx.AsyncClient, api_key: str):
        self._client = client
        self._api_key = api_key

    async def search(
        self, query: str, published_after: datetime, max_results: int = 50
    ) -> list[Video]:
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
        videos: list[Video] = []
        for item in data.get("items", []):
            try:
                snippet = item["snippet"]
                videos.append(
                    Video(
                        video_id=item["id"]["videoId"],
                        title=snippet["title"],
                        published_at=_parse_rfc3339(snippet["publishedAt"]),
                        channel_title=snippet.get("channelTitle", ""),
                    )
                )
            except Exception:
                logger.exception("failed to parse search item: query=%r", query)
        logger.info("api search: query=%r count=%d units=%d", query, len(videos), SEARCH_COST)
        return videos

    async def _get(self, endpoint: str, params: dict) -> dict:
        """GET with exponential backoff."""
        backoff = INITIAL_BACKOFF_SECONDS
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self._client.get(
                    f"{API_BASE}/{endpoint}", params=params, timeout=20.0
                )
                response.raise_for_status()
                return response.json()
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


def _parse_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
