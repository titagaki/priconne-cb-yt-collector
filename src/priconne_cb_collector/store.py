"""SQLite 永続化。投稿に成功した動画と、収集期間の状態だけを持つ。

Only successful posts are recorded, so a video that failed to post is simply
found again by the next search round and retried. That is what removes the
need for a pending/posted state machine.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class Period:
    """A collection period: opened by /start, closed by /stop. No end date."""

    start: datetime  # aware
    cb_period: str  # "YYYY-MM"


def period_key(started_at: datetime) -> str:
    """The key a run belongs to: the JST month it was started in."""
    local = started_at.astimezone(JST)
    return f"{local.year:04d}-{local.month:02d}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS posted_videos (
  video_id   TEXT PRIMARY KEY,
  title      TEXT NOT NULL,
  boss_index INTEGER,
  posted_at  TEXT NOT NULL,
  cb_period  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posted_period ON posted_videos(cb_period);

CREATE TABLE IF NOT EXISTS period_state (
  cb_period TEXT PRIMARY KEY,
  start_at  TEXT,
  is_open   INTEGER DEFAULT 0
);
"""


class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._conn:
            yield self._conn

    # ---- posted videos ----

    def known_video_ids(self, video_ids: list[str]) -> set[str]:
        """Which of these have already been posted."""
        if not video_ids:
            return set()
        placeholders = ",".join("?" * len(video_ids))
        cur = self._conn.execute(
            f"SELECT video_id FROM posted_videos WHERE video_id IN ({placeholders})", video_ids
        )
        return {row["video_id"] for row in cur.fetchall()}

    def mark_posted(
        self,
        video_id: str,
        title: str,
        boss_index: int | None,
        cb_period: str,
        now: datetime | None = None,
    ) -> None:
        """Only ever called after Discord confirms the message."""
        with self._tx() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO posted_videos "
                "(video_id, title, boss_index, posted_at, cb_period) VALUES (?,?,?,?,?)",
                (
                    video_id,
                    title,
                    boss_index,
                    _to_utc_iso(now or datetime.now(UTC)),
                    cb_period,
                ),
            )

    def count_by_boss(self, cb_period: str) -> dict[int | None, int]:
        cur = self._conn.execute(
            "SELECT boss_index, COUNT(*) AS n FROM posted_videos WHERE cb_period = ? "
            "GROUP BY boss_index",
            (cb_period,),
        )
        return {row["boss_index"]: row["n"] for row in cur.fetchall()}

    # ---- period ----

    def open_period(self, start_at: datetime) -> Period:
        """/start: record the start time and mark the period open."""
        period = Period(start=start_at, cb_period=period_key(start_at))
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO period_state (cb_period, start_at, is_open) VALUES (?,?,1) "
                "ON CONFLICT(cb_period) DO UPDATE SET start_at = excluded.start_at, is_open = 1",
                (period.cb_period, _to_utc_iso(start_at)),
            )
        return period

    def close_period(self, cb_period: str) -> None:
        """/stop: back to idle without deleting collected data."""
        with self._tx() as conn:
            conn.execute("UPDATE period_state SET is_open = 0 WHERE cb_period = ?", (cb_period,))

    def current_period(self) -> Period | None:
        """The open period, or None while idle.

        Looked up by is_open rather than by today's month: a run started on the
        23rd stays open -- and keeps its July key -- after the month rolls over.
        """
        cur = self._conn.execute(
            "SELECT cb_period, start_at FROM period_state WHERE is_open = 1 "
            "ORDER BY start_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None or not row["start_at"]:
            return None
        return Period(start=_from_utc_iso(row["start_at"]), cb_period=row["cb_period"])


def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _from_utc_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)
