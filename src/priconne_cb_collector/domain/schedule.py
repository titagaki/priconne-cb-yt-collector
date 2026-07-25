"""Period computation and the collect / don't-collect decision. Pure functions.

Spec: docs/spec/04-schedule.md
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from priconne_cb_collector.domain.models import Period
from priconne_cb_collector.domain.settings import ScheduleConfig

JST = ZoneInfo("Asia/Tokyo")


def offset_period(year: int, month: int, sched: ScheduleConfig) -> Period:
    """Compute the period for a given month from its last day."""
    last_day = calendar.monthrange(year, month)[1]
    start = datetime(year, month, last_day - sched.start_offset_days, tzinfo=JST)
    end = datetime(year, month, last_day - sched.end_offset_days, 23, 59, 59, tzinfo=JST)
    return Period(start=start, end=end, cb_period=f"{year:04d}-{month:02d}")


def resolve_period(
    sched: ScheduleConfig,
    now: datetime,
    trigger_started_at: datetime | None = None,
) -> Period | None:
    """Return the current (or upcoming) period, or None if undeterminable.

    - offset:  this month's period; once past its end, next month's
    - manual:  the explicitly configured dates (None if not configured)
    - trigger: None until /start; then collection starts at the trigger time
               and the end date follows the offset formula for that month
    """
    if sched.mode == "offset":
        local = now.astimezone(JST)
        period = offset_period(local.year, local.month, sched)
        if now > period.end:
            year, month = _next_month(local.year, local.month)
            period = offset_period(year, month, sched)
        return period

    if sched.mode == "manual":
        if not sched.manual_start or not sched.manual_end:
            return None
        start = _parse_local_date(sched.manual_start)
        end = _parse_local_date(sched.manual_end) + timedelta(hours=23, minutes=59, seconds=59)
        return Period(
            start=start,
            end=end,
            cb_period=f"{start.year:04d}-{start.month:02d}",
        )

    if sched.mode == "trigger":
        if trigger_started_at is None:
            return None
        local = trigger_started_at.astimezone(JST)
        base = offset_period(local.year, local.month, sched)
        return Period(start=trigger_started_at, end=base.end, cb_period=base.cb_period)

    raise ValueError(f"unknown schedule mode: {sched.mode}")


def is_collecting(now: datetime, period: Period | None) -> bool:
    """The only phase question the bot asks: collect now, or stay quiet?"""
    if period is None:
        return False
    return period.start <= now <= period.end


def should_remind(
    sched: ScheduleConfig,
    now: datetime,
    trigger_started: bool,
    already_reminded: bool,
) -> bool:
    """Whether to post a "/start reminder" (11-1 decision).

    Only in trigger mode: once the offset-computed start has passed without
    /start, remind exactly once per period (the caller persists the flag in
    period_state.notified_reminder).
    """
    if sched.mode != "trigger" or not sched.remind_if_not_started:
        return False
    if trigger_started or already_reminded:
        return False
    local = now.astimezone(JST)
    period = offset_period(local.year, local.month, sched)
    return period.start <= now <= period.end


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _parse_local_date(value: str | date) -> datetime:
    """YAML may hand us a str or an already-parsed date. Midnight JST."""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return datetime(value.year, value.month, value.day, tzinfo=JST)
