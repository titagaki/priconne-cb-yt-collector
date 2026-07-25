"""schedule.py のテスト（docs/spec/10 の必須ケース）。"""

from datetime import UTC, datetime, timedelta

import pytest

from priconne_cb_collector.domain.models import PHASE_BATTLE, PHASE_IDLE, PHASE_TRAINING
from priconne_cb_collector.domain.schedule import (
    JST,
    offset_period,
    phase_at,
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
    ("year", "month", "training", "battle_start", "battle_end_day"),
    [
        (2026, 7, 23, 26, 30),  # 末日31
        (2026, 6, 22, 25, 29),  # 末日30
        (2026, 2, 20, 23, 27),  # 末日28
        (2028, 2, 21, 24, 28),  # 末日29（閏年）
    ],
)
def test_offset_period_month_lengths(year, month, training, battle_start, battle_end_day):
    p = offset_period(year, month, OFFSET)
    assert p.training_start == jst(year, month, training)
    assert p.battle_start == jst(year, month, battle_start)
    assert p.battle_end == jst(year, month, battle_end_day, 23, 59, 59)
    assert p.cb_period == f"{year:04d}-{month:02d}"


# ---- 3フェーズの境界（前後1秒） ----


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (jst(2026, 7, 22, 23, 59, 59), PHASE_IDLE),  # トレモ開始 1秒前
        (jst(2026, 7, 23, 0, 0, 0), PHASE_TRAINING),  # トレモ開始ちょうど
        (jst(2026, 7, 23, 0, 0, 1), PHASE_TRAINING),  # トレモ開始 1秒後
        (jst(2026, 7, 25, 23, 59, 59), PHASE_TRAINING),  # 本番開始 1秒前
        (jst(2026, 7, 26, 0, 0, 0), PHASE_BATTLE),  # 本番開始ちょうど
        (jst(2026, 7, 26, 0, 0, 1), PHASE_BATTLE),  # 本番開始 1秒後
        (jst(2026, 7, 30, 23, 59, 58), PHASE_BATTLE),  # 終了 1秒前
        (jst(2026, 7, 30, 23, 59, 59), PHASE_BATTLE),  # 終了時刻ちょうど（含む）
        (jst(2026, 7, 31, 0, 0, 0), PHASE_IDLE),  # 終了 1秒後
    ],
)
def test_phase_boundaries(now, expected):
    p = offset_period(2026, 7, OFFSET)
    assert phase_at(now, p) == expected


# ---- 月またぎ ----


def test_offset_rolls_over_to_next_month_after_end():
    now = jst(2026, 7, 31, 12, 0, 0)  # 7月期間の終了後
    p = resolve_period(OFFSET, now)
    assert p.cb_period == "2026-08"
    assert phase_at(now, p) == PHASE_IDLE


def test_offset_rolls_over_year_boundary():
    now = jst(2026, 12, 31, 12, 0, 0)  # 12月期間（26〜30日）終了後
    p = resolve_period(OFFSET, now)
    assert p.cb_period == "2027-01"


def test_offset_within_period_stays_in_current_month():
    now = jst(2026, 7, 26, 12, 0, 0)
    p = resolve_period(OFFSET, now)
    assert p.cb_period == "2026-07"
    assert phase_at(now, p) == PHASE_BATTLE


# ---- manual モード ----

MANUAL = ScheduleConfig(
    mode="manual",
    manual_training_start="2026-07-21",
    manual_battle_start="2026-07-24",
    manual_end="2026-07-28",
)


def test_manual_mode_uses_explicit_dates():
    p = resolve_period(MANUAL, jst(2026, 7, 22))
    assert p.training_start == jst(2026, 7, 21)
    assert p.battle_start == jst(2026, 7, 24)
    assert p.battle_end == jst(2026, 7, 28, 23, 59, 59)
    assert p.cb_period == "2026-07"


def test_manual_mode_training_null_falls_back_to_battle_start():
    sched = ScheduleConfig(mode="manual", manual_battle_start="2026-07-24", manual_end="2026-07-28")
    p = resolve_period(sched, jst(2026, 7, 22))
    assert p.training_start == p.battle_start


def test_manual_mode_unconfigured_is_idle():
    sched = ScheduleConfig(mode="manual")
    assert resolve_period(sched, jst(2026, 7, 22)) is None
    assert phase_at(jst(2026, 7, 22), None) == PHASE_IDLE


# ---- trigger モード ----


def test_trigger_mode_idle_until_started():
    assert resolve_period(TRIGGER, jst(2026, 7, 25)) is None
    assert phase_at(jst(2026, 7, 25), None) == PHASE_IDLE


def test_trigger_mode_training_starts_at_trigger_time():
    started = jst(2026, 7, 23, 14, 30, 0)
    p = resolve_period(TRIGGER, jst(2026, 7, 23, 15, 0), trigger_started_at=started)
    assert p.training_start == started
    # battle は offset 式（末日31 → 26〜30日）
    assert p.battle_start == jst(2026, 7, 26)
    assert p.battle_end == jst(2026, 7, 30, 23, 59, 59)
    assert phase_at(jst(2026, 7, 23, 14, 30), p) == PHASE_TRAINING
    assert phase_at(jst(2026, 7, 23, 14, 29, 59), p) == PHASE_IDLE


def test_trigger_started_late_goes_straight_to_battle():
    started = jst(2026, 7, 27, 10, 0, 0)  # 本番中に /start
    p = resolve_period(TRIGGER, started, trigger_started_at=started)
    assert phase_at(started, p) == PHASE_BATTLE


# ---- 再起動時のフェーズ再計算 ----


def test_restart_recomputes_same_phase():
    """resolve_period は純粋関数なので、再起動後も同じ入力から同じ期間を得る。"""
    started = jst(2026, 7, 23, 9, 0, 0)
    before = resolve_period(TRIGGER, jst(2026, 7, 24), trigger_started_at=started)
    after_restart = resolve_period(TRIGGER, jst(2026, 7, 27), trigger_started_at=started)
    assert before == after_restart
    assert phase_at(jst(2026, 7, 24), after_restart) == PHASE_TRAINING
    assert phase_at(jst(2026, 7, 27), after_restart) == PHASE_BATTLE


# ---- /start 催促（11-1 決定） ----


@pytest.mark.parametrize(
    ("now", "started", "reminded", "expected"),
    [
        (jst(2026, 7, 22, 23, 59, 59), False, False, False),  # トレモ開始前
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


def test_phase_with_utc_input():

    p = offset_period(2026, 7, OFFSET)
    # 2026-07-23 00:00 JST == 2026-07-22 15:00 UTC
    utc_now = datetime(2026, 7, 22, 15, 0, 0, tzinfo=UTC)
    assert phase_at(utc_now, p) == PHASE_TRAINING
    assert phase_at(utc_now - timedelta(seconds=1), p) == PHASE_IDLE
