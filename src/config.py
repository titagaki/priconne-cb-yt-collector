"""Load and validate config/bosses.yaml and config/config.yaml."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from models import (
    AppConfig,
    Boss,
    BossesConfig,
    ChannelRef,
    ClassifyConfig,
    DiscordConfig,
    ExcludeConfig,
    PollingConfig,
    ScheduleConfig,
    YoutubeConfig,
)

logger = logging.getLogger(__name__)

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
REQUIRED_BOSS_COUNT = 5
MIN_ALIAS_LENGTH = 3  # shorter aliases cause false matches; warn only


class ConfigError(Exception):
    """Raised when a config file is invalid. Startup must fail."""


def load_bosses(path: str | Path) -> BossesConfig:
    data = _read_yaml(path)
    month = data.get("month")
    if not isinstance(month, str) or not MONTH_RE.match(month):
        raise ConfigError(f"bosses.yaml: 'month' must be 'YYYY-MM', got {month!r}")

    raw_bosses = data.get("bosses")
    if not isinstance(raw_bosses, list) or len(raw_bosses) != REQUIRED_BOSS_COUNT:
        count = len(raw_bosses) if isinstance(raw_bosses, list) else 0
        raise ConfigError(
            f"bosses.yaml: exactly {REQUIRED_BOSS_COUNT} bosses required, got {count}"
        )

    bosses: list[Boss] = []
    seen_indices: set[int] = set()
    for entry in raw_bosses:
        if not isinstance(entry, dict):
            raise ConfigError(f"bosses.yaml: boss entry must be a mapping, got {entry!r}")
        index = entry.get("index")
        name = entry.get("name")
        if not isinstance(index, int) or not (1 <= index <= REQUIRED_BOSS_COUNT):
            raise ConfigError(f"bosses.yaml: index must be 1-5, got {index!r}")
        if index in seen_indices:
            raise ConfigError(f"bosses.yaml: duplicate boss index {index}")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"bosses.yaml: boss {index} has no name")
        seen_indices.add(index)

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


def load_config(path: str | Path) -> AppConfig:
    data = _read_yaml(path)

    sched = data.get("schedule") or {}
    mode = sched.get("mode", "trigger")
    if mode not in ("offset", "manual", "trigger"):
        raise ConfigError(f"config.yaml: schedule.mode must be offset/manual/trigger, got {mode!r}")

    youtube = data.get("youtube") or {}
    exclude = youtube.get("exclude") or {}
    discord = data.get("discord") or {}
    layout = discord.get("layout", "per_boss_thread")
    if layout not in ("single", "per_boss_thread"):
        raise ConfigError(f"config.yaml: discord.layout must be single/per_boss_thread, got {layout!r}")

    classify = data.get("classify") or {}
    on_unknown = classify.get("on_boss_unknown", "skip")
    if on_unknown not in ("skip", "post_as_unknown"):
        raise ConfigError(
            f"config.yaml: classify.on_boss_unknown must be skip/post_as_unknown, got {on_unknown!r}"
        )

    polling = data.get("polling") or {}
    channels = tuple(
        ChannelRef(id=c["id"], name=c.get("name", ""))
        for c in (youtube.get("channels") or [])
    )

    return AppConfig(
        schedule=ScheduleConfig(
            mode=mode,
            start_offset_days=int(sched.get("start_offset_days", 5)),
            end_offset_days=int(sched.get("end_offset_days", 1)),
            training_days_before=int(sched.get("training_days_before", 3)),
            manual_training_start=sched.get("manual_training_start"),
            manual_battle_start=sched.get("manual_battle_start"),
            manual_end=sched.get("manual_end"),
            remind_if_not_started=bool(sched.get("remind_if_not_started", True)),
            search_lookback_days=int(sched.get("search_lookback_days", 1)),
        ),
        polling=PollingConfig(
            training_rss_interval_minutes=int(polling.get("training_rss_interval_minutes", 20)),
            training_api_search_interval_hours=int(
                polling.get("training_api_search_interval_hours", 6)
            ),
            rss_interval_minutes=int(polling.get("rss_interval_minutes", 10)),
            api_search_interval_hours=int(polling.get("api_search_interval_hours", 3)),
            idle_check_interval_minutes=int(polling.get("idle_check_interval_minutes", 60)),
        ),
        youtube=YoutubeConfig(
            channels=channels,
            search_query_base=youtube.get("search_query_base", "プリコネ クラバト"),
            quota_limit_per_day=int(youtube.get("quota_limit_per_day", 9000)),
            exclude=ExcludeConfig(
                min_duration_seconds=int(exclude.get("min_duration_seconds", 60)),
                max_duration_seconds=int(exclude.get("max_duration_seconds", 3600)),
                exclude_live=bool(exclude.get("exclude_live", True)),
                title_ng_words=tuple(exclude.get("title_ng_words") or ()),
            ),
        ),
        discord=DiscordConfig(
            layout=layout,
            channel_id=int(discord.get("channel_id", 0)),
            max_posts_per_boss_per_day=int(discord.get("max_posts_per_boss_per_day", 15)),
            post_interval_seconds=float(discord.get("post_interval_seconds", 2)),
        ),
        classify=ClassifyConfig(
            enable_ex_notation=bool(classify.get("enable_ex_notation", True)),
            on_boss_unknown=on_unknown,
        ),
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
