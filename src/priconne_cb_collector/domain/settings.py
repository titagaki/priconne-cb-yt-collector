"""Configuration schema. Plain dataclasses with no I/O and no dependencies.

Loading these from YAML is an adapter concern (adapters.config_file).
"""

from __future__ import annotations

from dataclasses import dataclass, field

LAYOUT_SINGLE = "single"
LAYOUT_PER_BOSS_THREAD = "per_boss_thread"

ON_UNKNOWN_SKIP = "skip"
ON_UNKNOWN_POST = "post_as_unknown"


@dataclass(frozen=True)
class PollingConfig:
    """One cadence for the whole collection period: there is no training /
    battle split, and no idle cadence because the loop does not run while
    stopped (docs/spec/04)."""

    rss_interval_minutes: int = 30
    api_search_interval_hours: int = 3


@dataclass(frozen=True)
class ChannelRef:
    id: str
    name: str = ""


@dataclass(frozen=True)
class ExcludeConfig:
    min_duration_seconds: int = 60
    max_duration_seconds: int = 3600
    exclude_live: bool = True
    title_ng_words: tuple[str, ...] = ()


@dataclass(frozen=True)
class YoutubeConfig:
    channels: tuple[ChannelRef, ...] = ()
    quota_limit_per_day: int = 9000
    # How far before /start the API search reaches back (search.list publishedAfter)
    search_lookback_days: int = 1
    exclude: ExcludeConfig = field(default_factory=ExcludeConfig)


@dataclass(frozen=True)
class DiscordConfig:
    layout: str = LAYOUT_PER_BOSS_THREAD
    channel_id: int = 0
    max_posts_per_boss_per_day: int = 15
    post_interval_seconds: float = 2.0


@dataclass(frozen=True)
class ClassifyConfig:
    enable_ex_notation: bool = True
    on_boss_unknown: str = ON_UNKNOWN_POST


@dataclass(frozen=True)
class AppConfig:
    polling: PollingConfig = field(default_factory=PollingConfig)
    youtube: YoutubeConfig = field(default_factory=YoutubeConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    classify: ClassifyConfig = field(default_factory=ClassifyConfig)
