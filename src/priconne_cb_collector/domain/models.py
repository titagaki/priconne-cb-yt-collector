"""Domain entities. Plain dataclasses with no I/O and no dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

PHASE_IDLE = "idle"
PHASE_TRAINING = "training"
PHASE_BATTLE = "battle"

BATTLE_NORMAL = "normal"
BATTLE_CARRYOVER = "carryover"
BATTLE_UNKNOWN = "unknown"

MATCH_BOSS_NAME = "boss_name"
MATCH_EX_NOTATION = "ex_notation"

EVIDENCE_KEYWORD = "keyword"
EVIDENCE_PHASE_ONLY = "phase_only"


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
class Period:
    """Active collection period. All datetimes are timezone-aware."""

    training_start: datetime
    battle_start: datetime
    battle_end: datetime  # inclusive (23:59:59 JST of the last battle day)
    cb_period: str  # "YYYY-MM"


@dataclass
class VideoMeta:
    """A video from RSS or API search, enriched via videos.list."""

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
    match_source: str | None = None  # MATCH_BOSS_NAME | MATCH_EX_NOTATION | None
    matched_strings: list[str] = field(default_factory=list)
    is_summary: bool = False

    @property
    def primary_index(self) -> int | None:
        return self.indices[0] if self.indices else None


@dataclass
class Classification:
    boss: BossMatch = field(default_factory=BossMatch)
    battle_type: str = BATTLE_UNKNOWN
    carryover_sec: int | None = None
    boss_phase: int | None = None  # boss strengthening phase 1-5, not bot phase
    damage: int | None = None  # normalized to units of 万
    is_full_auto: bool | None = None
    is_manual: bool | None = None
    is_training_footage: bool = False
    training_evidence: str | None = None  # EVIDENCE_KEYWORD | EVIDENCE_PHASE_ONLY | None
