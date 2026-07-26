"""Domain entities. Plain dataclasses with no I/O and no dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

BATTLE_NORMAL = "normal"
BATTLE_CARRYOVER = "carryover"
BATTLE_UNKNOWN = "unknown"

MATCH_BOSS_NAME = "boss_name"
MATCH_EX_NOTATION = "ex_notation"


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
    """Collection period. All datetimes are timezone-aware.

    Opened by /start and closed by /stop; there is no end date and no
    training/battle split. The bot is either collecting or it is not
    (docs/spec/04).
    """

    start: datetime
    cb_period: str  # "YYYY-MM"


@dataclass
class VideoMeta:
    """A video found by API search, enriched via videos.list."""

    video_id: str
    title: str
    channel_id: str
    published_at: datetime  # aware UTC
    description: str = ""
    channel_title: str = ""
    duration_sec: int | None = None
    view_count: int | None = None
    is_live: bool = False


@dataclass
class BossMatch:
    """Raw hits from the classifier. All hits are kept here for logging;
    only a single-boss hit is considered decided (docs/spec/06 §2.1).
    """

    indices: list[int] = field(default_factory=list)
    match_source: str | None = None  # MATCH_BOSS_NAME | MATCH_EX_NOTATION | None
    matched_strings: list[str] = field(default_factory=list)

    @property
    def decided_index(self) -> int | None:
        """The boss to store. Multiple hits mean we cannot tell which one."""
        return self.indices[0] if len(self.indices) == 1 else None

    @property
    def decided_source(self) -> str | None:
        """The route that decided the boss; meaningless when undecided."""
        return self.match_source if self.decided_index is not None else None


@dataclass
class Classification:
    boss: BossMatch = field(default_factory=BossMatch)
    battle_type: str = BATTLE_UNKNOWN
    carryover_sec: int | None = None
    damage: int | None = None  # normalized to units of 万
