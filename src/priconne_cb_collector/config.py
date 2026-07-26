"""設定の読み込み（config.yaml / bosses.yaml）。

Loading and validation live together: there is not enough of either to
justify splitting the schema from the reader.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
BOSS_COUNT = 5
MIN_ALIAS_LENGTH = 3  # shorter aliases cause false matches; warn only


class ConfigError(Exception):
    """Raised when a config file is invalid. Startup must fail."""


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
class Config:
    search_interval_minutes: int = 30
    # How far before /start the search reaches back (search.list publishedAfter)
    search_lookback_days: int = 1
    title_ng_words: tuple[str, ...] = ()
    post_interval_seconds: float = 2.0
    # Existing channels, given by the operator. The bot never creates them.
    boss_channels: dict[int, int] = field(default_factory=dict)
    fallback_channel_id: int = 0

    def channel_for(self, boss_index: int | None) -> int:
        """Where a video goes. Undecided ones fall back to the general channel."""
        if boss_index is None:
            return self.fallback_channel_id
        return self.boss_channels.get(boss_index, self.fallback_channel_id)


def load_bosses(path: str | Path) -> BossesConfig:
    data = _read_yaml(path)
    month = data.get("month")
    if not isinstance(month, str) or not MONTH_RE.match(month):
        raise ConfigError(f"bosses.yaml: 'month' must be 'YYYY-MM', got {month!r}")

    raw = data.get("bosses")
    if not isinstance(raw, list) or len(raw) != BOSS_COUNT:
        count = len(raw) if isinstance(raw, list) else 0
        raise ConfigError(f"bosses.yaml: exactly {BOSS_COUNT} bosses required, got {count}")

    bosses: list[Boss] = []
    seen: set[int] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ConfigError(f"bosses.yaml: boss entry must be a mapping, got {entry!r}")
        index = entry.get("index")
        name = entry.get("name")
        if not isinstance(index, int) or not (1 <= index <= BOSS_COUNT):
            raise ConfigError(f"bosses.yaml: index must be 1-5, got {index!r}")
        if index in seen:
            raise ConfigError(f"bosses.yaml: duplicate boss index {index}")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"bosses.yaml: boss {index} has no name")
        seen.add(index)

        aliases = entry.get("aliases") or [name]
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise ConfigError(f"bosses.yaml: boss {index} aliases must be a list of strings")
        for alias in aliases:
            if len(alias) < MIN_ALIAS_LENGTH:
                logger.warning(
                    "short alias may cause false matches: boss=%s alias=%r", index, alias
                )
        bosses.append(Boss(index=index, name=name, aliases=tuple(aliases)))

    bosses.sort(key=lambda b: b.index)
    return BossesConfig(month=month, bosses=tuple(bosses))


def load_config(path: str | Path) -> Config:
    data = _read_yaml(path)
    discord = data.get("discord") or {}
    youtube = data.get("youtube") or {}

    fallback = int(discord.get("fallback_channel_id", 0))
    if not fallback:
        raise ConfigError("config.yaml: discord.fallback_channel_id is required")

    raw_channels = discord.get("boss_channels") or {}
    if not isinstance(raw_channels, dict):
        raise ConfigError(
            "config.yaml: discord.boss_channels must be a mapping of 1-5 to channel id"
        )
    boss_channels: dict[int, int] = {}
    for key, value in raw_channels.items():
        index = int(key)
        if not (1 <= index <= BOSS_COUNT):
            raise ConfigError(f"config.yaml: boss_channels key must be 1-5, got {key!r}")
        boss_channels[index] = int(value)

    missing = [i for i in range(1, BOSS_COUNT + 1) if i not in boss_channels]
    if missing:
        # Not fatal: those bosses simply post to the fallback channel.
        logger.warning("boss_channels not set for %s; using the fallback channel", missing)

    return Config(
        search_interval_minutes=int((data.get("polling") or {}).get("search_interval_minutes", 30)),
        search_lookback_days=int(youtube.get("search_lookback_days", 1)),
        title_ng_words=tuple(youtube.get("title_ng_words") or ()),
        post_interval_seconds=float(discord.get("post_interval_seconds", 2)),
        boss_channels=boss_channels,
        fallback_channel_id=fallback,
    )


def _read_yaml(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"config file is not a mapping: {path}")
    return data
