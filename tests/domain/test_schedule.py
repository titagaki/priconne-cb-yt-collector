"""schedule.py のテスト（docs/spec/10 の必須ケース）。"""

from datetime import UTC, datetime, timedelta

import pytest

from priconne_cb_collector.domain.schedule import (
    JST,
    is_collecting,
    offset_period,
    resolve_period,
    should_remind,
)
from priconne_cb_collector.domain.settings import ScheduleConfig

OFFSET = ScheduleConfig(mode="offset")
TRIGGER = ScheduleConfig(mode="trigger")


def jst(*args):
    return datetime(*args, tzinfo=JST)


# ---- offset: 月末 28 / 29 / 30 / 31 日の各パターン ----


@pytest.mark.parametrize(
    ("year", "month", "start_day", "end_day"),
    [
        (2026, 7, 23, 30),  # 末日31
        (2026, 6, 22, 29),  # 末日30
        (2026, 2, 20, 27),  # 末日28
        (2028, 2, 21, 28),  # 末日29（閏年）
    ],
)
def test_offset_period_month_lengths(year, month, start_day, end_day):
    p = offset_period(year, month, OFFSET)
    assert p.start == jst(year, month, start_day)
    assert p.end == jst(year, month, end_day, 23, 59, 59)
    assert p.cb_period == f"{year:04d}-{month:02d}"


# ---- 収集する / しないの境界（前後1秒） ----


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (jst(2026, 7, 22, 23, 59, 59), False),  # 開始 1秒前
        (jst(2026, 7, 23, 0, 0, 0), True),  # 開始ちょうど
        (jst(2026, 7, 23, 0, 0, 1), True),  # 開始 1秒後
        (jst(2026, 7, 26, 12, 0, 0), True),  # 期間の途中
        (jst(2026, 7, 30, 23, 59, 58), True),  # 終了 1秒前
        (jst(2026, 7, 30, 23, 59, 59), True),  # 終了時刻ちょうど（含む）
        (jst(2026, 7, 31, 0, 0, 0), False),  # 終了 1秒後
    ],
)
def test_collection_boundaries(now, expected):
    p = offset_period(2026, 7, OFFSET)
    assert is_collecting(now, p) is expected


def test_no_period_never_collects():
    assert is_collecting(jst(2026, 7, 26), None) is False


# ---- 月またぎ ----


def test_offset_rolls_over_to_next_month_after_end():
    now = jst(2026, 7, 31, 12, 0, 0)  # 7月期間の終了後
    p = resolve_period(OFFSET, now)
    assert p.cb_period == "2026-08"
    assert is_collecting(now, p) is False


def test_offset_rolls_over_year_boundary():
    now = jst(2026, 12, 31, 12, 0, 0)  # 12月期間（23〜30日）終了後
    p = resolve_period(OFFSET, now)
    assert p.cb_period == "2027-01"


def test_offset_within_period_stays_in_current_month():
    now = jst(2026, 7, 26, 12, 0, 0)
    p = resolve_period(OFFSET, now)
    assert p.cb_period == "2026-07"
    assert is_collecting(now, p) is True


# ---- manual モード ----

MANUAL = ScheduleConfig(mode="manual", manual_start="2026-07-21", manual_end="2026-07-28")


def test_manual_mode_uses_explicit_dates():
    p = resolve_period(MANUAL, jst(2026, 7, 22))
    assert p.start == jst(2026, 7, 21)
    assert p.end == jst(2026, 7, 28, 23, 59, 59)
    assert p.cb_period == "2026-07"


def test_manual_mode_unconfigured_is_idle():
    sched = ScheduleConfig(mode="manual")
    assert resolve_period(sched, jst(2026, 7, 22)) is None


def test_manual_mode_requires_both_ends():
    only_start = ScheduleConfig(mode="manual", manual_start="2026-07-21")
    only_end = ScheduleConfig(mode="manual", manual_end="2026-07-28")
    assert resolve_period(only_start, jst(2026, 7, 22)) is None
    assert resolve_period(only_end, jst(2026, 7, 22)) is None


# ---- trigger モード ----


def test_trigger_mode_idle_until_started():
    assert resolve_period(TRIGGER, jst(2026, 7, 25)) is None


def test_trigger_mode_collection_starts_at_trigger_time():
    started = jst(2026, 7, 23, 14, 30, 0)
    p = resolve_period(TRIGGER, jst(2026, 7, 23, 15, 0), trigger_started_at=started)
    assert p.start == started
    # 終了日は offset 式（末日31 → 30日）
    assert p.end == jst(2026, 7, 30, 23, 59, 59)
    assert is_collecting(jst(2026, 7, 23, 14, 30), p) is True
    assert is_collecting(jst(2026, 7, 23, 14, 29, 59), p) is False


def test_trigger_started_late_still_collects_immediately():
    started = jst(2026, 7, 27, 10, 0, 0)  # 期間の後半に /start
    p = resolve_period(TRIGGER, started, trigger_started_at=started)
    assert is_collecting(started, p) is True


# ---- 再起動時の再計算 ----


def test_restart_recomputes_same_period():
    """resolve_period は純粋関数なので、再起動後も同じ入力から同じ期間を得る。"""
    started = jst(2026, 7, 23, 9, 0, 0)
    before = resolve_period(TRIGGER, jst(2026, 7, 24), trigger_started_at=started)
    after_restart = resolve_period(TRIGGER, jst(2026, 7, 27), trigger_started_at=started)
    assert before == after_restart
    assert is_collecting(jst(2026, 7, 27), after_restart) is True


# ---- /start 催促（11-1 決定） ----


@pytest.mark.parametrize(
    ("now", "started", "reminded", "expected"),
    [
        (jst(2026, 7, 22, 23, 59, 59), False, False, False),  # 開始前
        (jst(2026, 7, 23, 0, 0, 0), False, False, True),  # 開始日時を過ぎて未 start
        (jst(2026, 7, 25), False, True, False),  # 催促済み
        (jst(2026, 7, 25), True, False, False),  # /start 済み
        (jst(2026, 7, 31), False, False, False),  # 期間終了後は催促しない
    ],
)
def test_should_remind(now, started, reminded, expected):
    assert should_remind(TRIGGER, now, started, reminded) is expected


def test_should_remind_disabled_by_config_or_mode():
    now = jst(2026, 7, 25)
    assert should_remind(ScheduleConfig(mode="offset"), now, False, False) is False
    no_remind = ScheduleConfig(mode="trigger", remind_if_not_started=False)
    assert should_remind(no_remind, now, False, False) is False


# ---- タイムゾーン: UTC で渡しても JST 基準で判定される ----


def test_collecting_with_utc_input():
    p = offset_period(2026, 7, OFFSET)
    # 2026-07-23 00:00 JST == 2026-07-22 15:00 UTC
    utc_now = datetime(2026, 7, 22, 15, 0, 0, tzinfo=UTC)
    assert is_collecting(utc_now, p) is True
    assert is_collecting(utc_now - timedelta(seconds=1), p) is False
