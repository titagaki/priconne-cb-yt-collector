"""Channel RSS polling (docs/spec/05 §1). Costs no API quota.

Returns at most the 15 latest videos per channel and carries no description,
duration or view count — those come from videos.list (youtube_api.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
import httpx

from models import ChannelRef, VideoMeta

logger = logging.getLogger(__name__)

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
DISCOVERED_VIA = "rss"


async def fetch_channel(
    client: httpx.AsyncClient,
    channel: ChannelRef,
    etag: str | None = None,
    last_fetch: str | None = None,
) -> tuple[list[VideoMeta], str | None, bool]:
    """Fetch one channel feed.

    Returns (videos, new_etag, not_modified). On 304 the video list is empty.
    """
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_fetch:
        headers["If-Modified-Since"] = _to_http_date(last_fetch)

    response = await client.get(
        FEED_URL.format(channel_id=channel.id), headers=headers, timeout=20.0
    )
    if response.status_code == 304:
        logger.debug("rss not modified: channel_id=%s", channel.id)
        return [], etag, True
    response.raise_for_status()

    feed = feedparser.parse(response.text)
    videos: list[VideoMeta] = []
    for entry in feed.entries:
        try:
            videos.append(_entry_to_video(entry, channel))
        except Exception:  # one malformed entry must not drop the whole feed
            logger.exception("failed to parse rss entry: channel_id=%s", channel.id)
    logger.info("rss fetched: channel_id=%s count=%d", channel.id, len(videos))
    return videos, response.headers.get("ETag", etag), False


def _entry_to_video(entry, channel: ChannelRef) -> VideoMeta:
    video_id = getattr(entry, "yt_videoid", None) or entry.id.split(":")[-1]
    published = datetime.fromisoformat(entry.published).astimezone(timezone.utc)
    return VideoMeta(
        video_id=video_id,
        title=entry.title,
        channel_id=getattr(entry, "yt_channelid", channel.id),
        published_at=published,
        discovered_via=DISCOVERED_VIA,
        channel_title=getattr(entry, "author", channel.name),
    )


def _to_http_date(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc).astimezone(timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
