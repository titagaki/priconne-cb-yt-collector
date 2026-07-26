"""Period lifecycle: whether a period is open, and what still needs announcing.

Spec: docs/spec/04. Holds no Discord objects, so the transition rules can be
tested without a bot client.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from priconne_cb_collector.adapters.sqlite_store import Store
from priconne_cb_collector.domain.models import Period
from priconne_cb_collector.domain.schedule import (
    JST,
    candidate_period_keys,
    is_collecting,
    make_period,
)

logger = logging.getLogger(__name__)


class PeriodService:
    """Owns the open period and the notification flags that guard against
    duplicate announcements across restarts.

    The period lives in the database, not in memory: a restart resumes an open
    period instead of forgetting it (docs/spec/04 §3).
    """

    def __init__(self, store: Store):
        self.store = store

    # ---- resolution ----

    def current_period(self, now: datetime | None = None) -> Period | None:
        """The open period, or None while stopped.

        A period started late in the month can still be open after the month
        rolls over, so the previous key is checked too.
        """
        now = now or datetime.now(UTC)
        for cb_period in candidate_period_keys(now.astimezone(JST)):
            started = self.store.open_period_start(cb_period)
            if started is not None:
                return Period(start=started, cb_period=cb_period)
        return None

    def is_collecting(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return is_collecting(now, self.current_period(now))

    # ---- transitions driven by commands ----

    def start(self, now: datetime) -> Period:
        """/start: collect from this moment on (docs/spec/09 §2)."""
        period = make_period(now)
        self.store.open_period(period)
        logger.info("period started: cb_period=%s", period.cb_period)
        return period

    def stop(self, now: datetime | None = None) -> Period | None:
        """/stop: the only way a period ends. None if nothing was open."""
        period = self.current_period(now)
        if period is None:
            return None
        self.store.close_period(period.cb_period)
        logger.info("period stopped: cb_period=%s", period.cb_period)
        return period

    # ---- notification bookkeeping ----

    def claim_notice(self, cb_period: str, kind: str) -> bool:
        """Reserve a one-shot notification. False means it was already sent,
        which is what keeps a restart from re-announcing (docs/spec/04 §3)."""
        return self.store.mark_notified(cb_period, kind)
