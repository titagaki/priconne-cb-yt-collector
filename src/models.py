"""Shared dataclasses for config, schedule and classification results."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

PHASE_IDLE = "idle"
PHASE_TRAINING = "training"
PHASE_BATTLE = "battle"


@dataclass(frozen=True)
class Boss:
    index: int
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class BossesConfig:
    month: str  # "YYYY-MM"
    bosses: tuple[Boss, ...]

    def by_index(self, index: int) -> Boss:
        for boss in self.bosses:
            if boss.index == index:
                return boss
        raise KeyError(index)


@dataclass(frozen=True)
class ScheduleConfig:
    mode: str = "trigger"  # "offset" | "manual" | "trigger"
    start_offset_days: int = 5
    end_offset_days: int = 1
    training_days_before: int = 3
    manual_training_start: str | None = None  # "YYYY-MM-DD"
    manual_battle_start: str | None = None
    manual_end: str | None = None
    remind_if_not_started: bool = True
    search_lookback_days: int = 1


@dataclass(frozen=True)
class PollingConfig:
    training_rss_interval_minutes: int = 20
    training_api_search_interval_hours: int = 6
    rss_interval_minutes: int = 10
    api_search_interval_hours: int = 3
    idle_check_interval_minutes: int = 60


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
    search_query_base: str = "プリコネ クラバト"
    quota_limit_per_day: int = 9000
    exclude: ExcludeConfig = field(default_factory=ExcludeConfig)


@dataclass(frozen=True)
class DiscordConfig:
    layout: str = "per_boss_thread"  # "single" | "per_boss_thread"
    channel_id: int = 0
    max_posts_per_boss_per_day: int = 15
    post_interval_seconds: float = 2.0


@dataclass(frozen=True)
class ClassifyConfig:
    enable_ex_notation: bool = True
    on_boss_unknown: str = "skip"  # "skip" | "post_as_unknown"


@dataclass(frozen=True)
class AppConfig:
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    youtube: YoutubeConfig = field(default_factory=YoutubeConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    classify: ClassifyConfig = field(default_factory=ClassifyConfig)


@dataclass(frozen=True)
class Period:
    """Active collection period. All datetimes are timezone-aware (JST)."""

    training_start: datetime
    battle_start: datetime
    battle_end: datetime  # inclusive (23:59:59 JST of the last battle day)
    cb_period: str  # "YYYY-MM"


@dataclass
class VideoMeta:
    """A video merged from RSS / API search, enriched via videos.list."""

    video_id: str
    title: str
    channel_id: str
    published_at: datetime  # aware UTC
    discovered_via: str  # "rss" | "api_search"
    description: str = ""
    channel_title: str = ""
    duration_sec: int | None = None
    view_count: int | None = None
    is_live: bool = False


@dataclass
class BossMatch:
    indices: list[int] = field(default_factory=list)
    match_source: str | None = None  # "boss_name" | "ex_notation" | None
    matched_strings: list[str] = field(default_factory=list)
    is_summary: bool = False

    @property
    def primary_index(self) -> int | None:
        return self.indices[0] if self.indices else None


@dataclass
class Classification:
    boss: BossMatch = field(default_factory=BossMatch)
    battle_type: str = "unknown"  # "normal" | "carryover" | "unknown"
    carryover_sec: int | None = None
    boss_phase: int | None = None  # boss strengthening phase 1-5, not bot phase
    damage: int | None = None  # normalized to units of 万
    is_full_auto: bool | None = None
    is_manual: bool | None = None
    is_training_footage: bool = False
    training_evidence: str | None = None  # "keyword" | "phase_only" | None
