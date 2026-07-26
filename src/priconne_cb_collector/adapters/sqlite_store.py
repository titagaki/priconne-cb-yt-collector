"""SQLite persistence (docs/spec/07).

Datetimes are stored as ISO8601 UTC; only quota_usage.date is a JST date.
Deduplication relies solely on the video_id primary key.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from priconne_cb_collector.domain.models import Classification, Period, VideoMeta
from priconne_cb_collector.domain.schedule import JST

STATUS_PENDING = "pending"
STATUS_POSTED = "posted"
STATUS_FILTERED = "filtered"
STATUS_ERROR = "error"

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  video_id        TEXT PRIMARY KEY,
  title           TEXT NOT NULL,
  description     TEXT,
  channel_id      TEXT NOT NULL,
  channel_title   TEXT,
  published_at    TEXT NOT NULL,
  duration_sec    INTEGER,
  view_count      INTEGER,
  discovered_at   TEXT NOT NULL,

  boss_index      INTEGER,
  match_source    TEXT,

  battle_type     TEXT,
  carryover_sec   INTEGER,
  damage          INTEGER,

  status          TEXT NOT NULL,
  filter_reason   TEXT,
  posted_at       TEXT,
  discord_msg_id  TEXT,
  cb_period       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_period_boss ON videos(cb_period, boss_index);

CREATE TABLE IF NOT EXISTS period_state (
  cb_period            TEXT PRIMARY KEY,
  start_at             TEXT,
  boss_thread_ids      TEXT,
  is_open              INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quota_usage (
  date        TEXT PRIMARY KEY,
  units_used  INTEGER NOT NULL DEFAULT 0
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

    # ---- videos ----

    def add_video(
        self,
        video: VideoMeta,
        classification: Classification,
        *,
        cb_period: str,
        status: str = STATUS_PENDING,
        filter_reason: str | None = None,
        discovered_at: datetime | None = None,
    ) -> bool:
        """Insert a video. Returns False if video_id already existed.

        Uses INSERT OR IGNORE so a re-discovered video never clobbers the
        existing row (and in particular never resets a "posted" status).
        """
        boss = classification.boss
        row = (
            video.video_id,
            video.title,
            video.description,
            video.channel_id,
            video.channel_title,
            _to_utc_iso(video.published_at),
            video.duration_sec,
            video.view_count,
            _to_utc_iso(discovered_at or datetime.now(UTC)),
            boss.decided_index,
            boss.decided_source,
            classification.battle_type,
            classification.carryover_sec,
            classification.damage,
            status,
            filter_reason,
            cb_period,
        )
        with self._tx() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO videos (
                  video_id, title, description, channel_id, channel_title,
                  published_at, duration_sec, view_count,
                  discovered_at, boss_index, match_source,
                  battle_type, carryover_sec, damage, status,
                  filter_reason, cb_period
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                row,
            )
        return cur.rowcount > 0

    def has_video(self, video_id: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,))
        return cur.fetchone() is not None

    def known_video_ids(self, video_ids: list[str]) -> set[str]:
        """Filter a candidate list down to the ids already stored."""
        if not video_ids:
            return set()
        placeholders = ",".join("?" * len(video_ids))
        cur = self._conn.execute(
            f"SELECT video_id FROM videos WHERE video_id IN ({placeholders})", video_ids
        )
        return {r["video_id"] for r in cur.fetchall()}

    def pending_videos(self, cb_period: str) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM videos WHERE status = ? AND cb_period = ? ORDER BY published_at",
            (STATUS_PENDING, cb_period),
        )
        return cur.fetchall()

    def get_video(self, video_id: str) -> sqlite3.Row | None:
        cur = self._conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
        return cur.fetchone()

    def mark_posted(
        self, video_id: str, discord_msg_id: str | int, now: datetime | None = None
    ) -> None:
        """Only ever called after a successful Discord post (docs/spec/08)."""
        with self._tx() as conn:
            conn.execute(
                "UPDATE videos SET status = ?, posted_at = ?, discord_msg_id = ? "
                "WHERE video_id = ?",
                (
                    STATUS_POSTED,
                    _to_utc_iso(now or datetime.now(UTC)),
                    str(discord_msg_id),
                    video_id,
                ),
            )

    def mark_filtered(self, video_id: str, reason: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE videos SET status = ?, filter_reason = ? WHERE video_id = ?",
                (STATUS_FILTERED, reason, video_id),
            )

    def mark_error(self, video_id: str, reason: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE videos SET status = ?, filter_reason = ? WHERE video_id = ?",
                (STATUS_ERROR, reason, video_id),
            )

    def count_posted_today(self, boss_index: int | None, now: datetime | None = None) -> int:
        """Posts made today (JST) for one boss, for the daily cap."""
        now = now or datetime.now(UTC)
        start_jst = now.astimezone(JST).replace(hour=0, minute=0, second=0, microsecond=0)
        if boss_index is None:
            cur = self._conn.execute(
                "SELECT COUNT(*) AS c FROM videos WHERE status = ? AND boss_index IS NULL "
                "AND posted_at >= ?",
                (STATUS_POSTED, _to_utc_iso(start_jst)),
            )
        else:
            cur = self._conn.execute(
                "SELECT COUNT(*) AS c FROM videos WHERE status = ? AND boss_index = ? "
                "AND posted_at >= ?",
                (STATUS_POSTED, boss_index, _to_utc_iso(start_jst)),
            )
        return cur.fetchone()["c"]

    def count_by_boss(self, cb_period: str) -> dict[int | None, int]:
        cur = self._conn.execute(
            "SELECT boss_index, COUNT(*) AS c FROM videos WHERE cb_period = ? GROUP BY boss_index",
            (cb_period,),
        )
        return {r["boss_index"]: r["c"] for r in cur.fetchall()}

    def recent_videos(self, cb_period: str, boss_index: int | None = None, limit: int = 10):
        if boss_index is None:
            cur = self._conn.execute(
                "SELECT * FROM videos WHERE cb_period = ? ORDER BY discovered_at DESC LIMIT ?",
                (cb_period, limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM videos WHERE cb_period = ? AND boss_index = ? "
                "ORDER BY discovered_at DESC LIMIT ?",
                (cb_period, boss_index, limit),
            )
        return cur.fetchall()

    # ---- period_state ----

    def ensure_period(self, period: Period, *, is_open: bool = False) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO period_state (cb_period, start_at, is_open) VALUES (?,?,?)",
                (period.cb_period, _to_utc_iso(period.start), int(is_open)),
            )

    def get_period_state(self, cb_period: str) -> sqlite3.Row | None:
        cur = self._conn.execute("SELECT * FROM period_state WHERE cb_period = ?", (cb_period,))
        return cur.fetchone()

    def open_period(self, period: Period) -> None:
        """Record a /start: overwrite the start time and mark the period open."""
        self.ensure_period(period, is_open=True)
        with self._tx() as conn:
            conn.execute(
                "UPDATE period_state SET start_at = ?, is_open = 1 WHERE cb_period = ?",
                (_to_utc_iso(period.start), period.cb_period),
            )

    def close_period(self, cb_period: str) -> None:
        """/stop: back to idle without deleting collected data."""
        with self._tx() as conn:
            conn.execute(
                "UPDATE period_state SET is_open = 0 WHERE cb_period = ?",
                (cb_period,),
            )

    def open_period_start(self, cb_period: str) -> datetime | None:
        """When the open period under this key was started, or None if closed."""
        row = self.get_period_state(cb_period)
        if row is None or not row["is_open"] or not row["start_at"]:
            return None
        return _from_utc_iso(row["start_at"])

    def save_boss_threads(self, cb_period: str, thread_ids: dict[int, int]) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE period_state SET boss_thread_ids = ? WHERE cb_period = ?",
                (json.dumps({str(k): v for k, v in thread_ids.items()}), cb_period),
            )

    def load_boss_threads(self, cb_period: str) -> dict[int, int]:
        row = self.get_period_state(cb_period)
        if row is None or not row["boss_thread_ids"]:
            return {}
        return {int(k): v for k, v in json.loads(row["boss_thread_ids"]).items()}

    # ---- quota ----

    def add_quota(self, units: int, now: datetime | None = None) -> int:
        """Add consumed units to today's (JST) tally and return the new total."""
        day = _jst_date(now)
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO quota_usage (date, units_used) VALUES (?, ?) "
                "ON CONFLICT(date) DO UPDATE SET units_used = units_used + ?",
                (day, units, units),
            )
        return self.quota_used(now)

    def quota_used(self, now: datetime | None = None) -> int:
        cur = self._conn.execute(
            "SELECT units_used FROM quota_usage WHERE date = ?", (_jst_date(now),)
        )
        row = cur.fetchone()
        return row["units_used"] if row else 0


def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _from_utc_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _jst_date(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return now.astimezone(JST).date().isoformat()
