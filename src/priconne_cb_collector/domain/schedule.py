"""Period construction and the collect / don't-collect decision. Pure functions.

Spec: docs/spec/04-schedule.md
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from priconne_cb_collector.domain.models import Period

JST = ZoneInfo("Asia/Tokyo")


def period_key(started_at: datetime) -> str:
    """The cb_period a run belongs to: the JST month it was started in.

    A run started late in the month keeps its key after the month rolls over,
    so everything collected in one clan battle stays under one key.
    """
    local = started_at.astimezone(JST)
    return f"{local.year:04d}-{local.month:02d}"


def make_period(started_at: datetime) -> Period:
    """The period opened by /start."""
    return Period(start=started_at, cb_period=period_key(started_at))


def is_collecting(now: datetime, period: Period | None) -> bool:
    """The only phase question the bot asks: collect now, or stay quiet?

    A period exists only while one is open, so this is just a None check plus
    a guard against a clock that reads earlier than the recorded start.
    """
    if period is None:
        return False
    return now >= period.start


def candidate_period_keys(local_now: datetime) -> list[str]:
    """This month's key plus the previous month's.

    A run started on the 23rd can still be open in the next month, so an open
    period must be looked for under both keys.
    """
    year, month = local_now.year, local_now.month
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    return [f"{year:04d}-{month:02d}", f"{prev_year:04d}-{prev_month:02d}"]
