"""Period lifecycle: which period is active, and what still needs announcing.

Spec: docs/spec/04. Holds no Discord objects, so the phase-transition rules
can be tested without a bot client.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime

from priconne_cb_collector.adapters.sqlite_store import Store
from priconne_cb_collector.domain.models import Period
from priconne_cb_collector.domain.schedule import (
    JST,
    offset_period,
    phase_at,
    resolve_period,
    should_remind,
)
from priconne_cb_collector.domain.settings import (
    MODE_MANUAL,
    MODE_TRIGGER,
    AppConfig,
    ScheduleConfig,
)

logger = logging.getLogger(__name__)


class PeriodService:
    """Owns the active period and the notification flags that guard against
    duplicate announcements across restarts."""

    def __init__(self, config: AppConfig, store: Store):
        self.config = config
        self.store = store

    @property
    def schedule(self) -> ScheduleConfig:
        return self.config.schedule

    # ---- resolution ----

    def current_period(self, now: datetime | None = None) -> Period | None:
        now = now or datetime.now(UTC)
        started = self.trigger_started_at(now) if self.schedule.mode == MODE_TRIGGER else None
        return resolve_period(self.schedule, now, started)

    def current_phase(self, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        return phase_at(now, self.current_period(now))

    def trigger_started_at(self, now: datetime | None = None) -> datetime | None:
        """The /start time, if any. A period started late in the month can still
        be running past the month boundary, so the previous key is checked too."""
        now = now or datetime.now(UTC)
        for cb_period in candidate_period_keys(now.astimezone(JST)):
            started = self.store.trigger_started_at(cb_period)
            if started is not None:
                return started
        return None

    def is_started(self, now: datetime | None = None) -> bool:
        return self.trigger_started_at(now) is not None

    # ---- transitions driven by commands ----

    def start(self, now: datetime) -> Period:
        """/start: collect from this moment on (docs/spec/09 §2)."""
        sched = replace(self.schedule, mode=MODE_TRIGGER)
        period = resolve_period(sched, now, trigger_started_at=now)
        self.store.set_trigger_start(period)
        self.config = replace(self.config, schedule=sched)
        logger.info("period started manually: cb_period=%s", period.cb_period)
        return period

    def stop(self, now: datetime | None = None) -> Period | None:
        period = self.current_period(now)
        if period is None:
            return None
        self.store.clear_trigger_start(period.cb_period)
        logger.info("period stopped manually: cb_period=%s", period.cb_period)
        return period

    def override(self, training_start, battle_start, end) -> Period:
        """/period set: switch to manual mode with explicit dates."""
        sched = replace(
            self.schedule,
            mode=MODE_MANUAL,
            manual_training_start=training_start,
            manual_battle_start=battle_start,
            manual_end=end,
        )
        period = resolve_period(sched, datetime.now(UTC))
        if period is None:
            raise ValueError("期間を解釈できませんでした")
        self.config = replace(self.config, schedule=sched)
        self.store.ensure_period(period)
        logger.info("period overridden manually: cb_period=%s", period.cb_period)
        return period

    # ---- notification bookkeeping ----

    def claim_notice(self, cb_period: str, kind: str) -> bool:
        """Reserve a one-shot notification. False means it was already sent,
        which is what keeps a restart from re-announcing (docs/spec/04 §3)."""
        return self.store.mark_notified(cb_period, kind)

    def pending_reminder(self, now: datetime | None = None) -> Period | None:
        """The period to nag about when /start was forgotten (11-1 decision).

        Returns None when a reminder is not due or was already sent.
        """
        now = now or datetime.now(UTC)
        local = now.astimezone(JST)
        offset = offset_period(local.year, local.month, self.schedule)
        if not should_remind(
            self.schedule,
            now,
            trigger_started=self.is_started(now),
            already_reminded=self.store.is_notified(offset.cb_period, "reminder"),
        ):
            return None
        self.store.ensure_period(offset)
        if not self.claim_notice(offset.cb_period, "reminder"):
            return None
        return offset


def candidate_period_keys(local_now: datetime) -> list[str]:
    """This month's key plus the previous month's."""
    year, month = local_now.year, local_now.month
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    return [f"{year:04d}-{month:02d}", f"{prev_year:04d}-{prev_month:02d}"]
