"""Period computation and phase decision. Pure functions, no I/O.

Spec: docs/spec/04-schedule.md
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from priconne_cb_collector.domain.models import (
    PHASE_BATTLE,
    PHASE_IDLE,
    PHASE_TRAINING,
    Period,
)
from priconne_cb_collector.domain.settings import ScheduleConfig

JST = ZoneInfo("Asia/Tokyo")


def offset_period(year: int, month: int, sched: ScheduleConfig) -> Period:
    """Compute the period for a given month from its last day."""
    last_day = calendar.monthrange(year, month)[1]
    battle_start = datetime(year, month, last_day - sched.start_offset_days, tzinfo=JST)
    battle_end = datetime(year, month, last_day - sched.end_offset_days, 23, 59, 59, tzinfo=JST)
    training_start = battle_start - timedelta(days=sched.training_days_before)
    return Period(
        training_start=training_start,
        battle_start=battle_start,
        battle_end=battle_end,
        cb_period=f"{year:04d}-{month:02d}",
    )


def resolve_period(
    sched: ScheduleConfig,
    now: datetime,
    trigger_started_at: datetime | None = None,
) -> Period | None:
    """Return the current (or upcoming) period, or None if undeterminable.

    - offset:  this month's period; once past its end, next month's
    - manual:  the explicitly configured dates (None if not configured)
    - trigger: None until /start; then training starts at the trigger time
               and battle dates follow the offset formula for that month
    """
    if sched.mode == "offset":
        local = now.astimezone(JST)
        period = offset_period(local.year, local.month, sched)
        if now > period.battle_end:
            year, month = _next_month(local.year, local.month)
            period = offset_period(year, month, sched)
        return period

    if sched.mode == "manual":
        if not sched.manual_battle_start or not sched.manual_end:
            return None
        battle_start = _parse_local_date(sched.manual_battle_start)
        battle_end = _parse_local_date(sched.manual_end) + timedelta(
            hours=23, minutes=59, seconds=59
        )
        if sched.manual_training_start:
            training_start = _parse_local_date(sched.manual_training_start)
        else:
            training_start = battle_start
        return Period(
            training_start=training_start,
            battle_start=battle_start,
            battle_end=battle_end,
            cb_period=f"{battle_start.year:04d}-{battle_start.month:02d}",
        )

    if sched.mode == "trigger":
        if trigger_started_at is None:
            return None
        local = trigger_started_at.astimezone(JST)
        base = offset_period(local.year, local.month, sched)
        return Period(
            training_start=trigger_started_at,
            battle_start=base.battle_start,
            battle_end=base.battle_end,
            cb_period=base.cb_period,
        )

    raise ValueError(f"unknown schedule mode: {sched.mode}")


def phase_at(now: datetime, period: Period | None) -> str:
    """Map a point in time onto idle / training / battle."""
    if period is None:
        return PHASE_IDLE
    if now < period.training_start:
        return PHASE_IDLE
    if now < period.battle_start:
        return PHASE_TRAINING
    if now <= period.battle_end:
        return PHASE_BATTLE
    return PHASE_IDLE


def should_remind(
    sched: ScheduleConfig,
    now: datetime,
    trigger_started: bool,
    already_reminded: bool,
) -> bool:
    """Whether to post a "/start reminder" (11-1 decision).

    Only in trigger mode: once the offset-computed training start has passed
    without /start, remind exactly once per period (the caller persists the
    flag in period_state.notified_reminder).
    """
    if sched.mode != "trigger" or not sched.remind_if_not_started:
        return False
    if trigger_started or already_reminded:
        return False
    local = now.astimezone(JST)
    period = offset_period(local.year, local.month, sched)
    return period.training_start <= now <= period.battle_end


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _parse_local_date(value: str | date) -> datetime:
    """YAML may hand us a str or an already-parsed date. Midnight JST."""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return datetime(value.year, value.month, value.day, tzinfo=JST)
