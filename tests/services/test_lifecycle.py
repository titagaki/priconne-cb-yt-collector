"""PeriodService のテスト（docs/spec/04）。Discord にも YouTube にも触れない。"""

from datetime import UTC, datetime

import pytest

from priconne_cb_collector.domain.models import PHASE_BATTLE, PHASE_IDLE, PHASE_TRAINING
from priconne_cb_collector.domain.settings import (
    MODE_MANUAL,
    MODE_OFFSET,
    MODE_TRIGGER,
    AppConfig,
    ScheduleConfig,
)
from priconne_cb_collector.services.lifecycle import PeriodService, candidate_period_keys
from tests.support import CB_PERIOD, freeze_now

TRAINING_NOW = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)  # JST 7/24 12:00
BATTLE_NOW = datetime(2026, 7, 27, 3, 0, tzinfo=UTC)
AFTER_END = datetime(2026, 7, 31, 3, 0, tzinfo=UTC)


def make_service(store, mode=MODE_TRIGGER, **schedule_kwargs):
    config = AppConfig(schedule=ScheduleConfig(mode=mode, **schedule_kwargs))
    return PeriodService(config, store)


# ---- 期間の解決 ----


def test_trigger_mode_is_idle_until_started(store):
    service = make_service(store)
    assert service.current_period(TRAINING_NOW) is None
    assert service.current_phase(TRAINING_NOW) == PHASE_IDLE
    assert service.is_started(TRAINING_NOW) is False


def test_start_records_the_period_and_switches_to_training(store):
    service = make_service(store)
    period = service.start(TRAINING_NOW)

    assert period.training_start == TRAINING_NOW
    assert period.cb_period == CB_PERIOD
    assert service.is_started(TRAINING_NOW) is True
    assert service.current_phase(TRAINING_NOW) == PHASE_TRAINING
    assert service.current_phase(BATTLE_NOW) == PHASE_BATTLE
    assert service.current_phase(AFTER_END) == PHASE_IDLE


def test_started_state_survives_a_new_service_instance(store):
    """再起動しても DB から /start 済みの状態を復元できること。"""
    make_service(store).start(TRAINING_NOW)

    restarted = make_service(store)
    assert restarted.is_started(BATTLE_NOW) is True
    assert restarted.current_period(BATTLE_NOW).training_start == TRAINING_NOW


def test_stop_returns_to_idle_without_deleting_data(store):
    service = make_service(store)
    service.start(TRAINING_NOW)

    stopped = service.stop(TRAINING_NOW)

    assert stopped.cb_period == CB_PERIOD
    assert service.current_period(TRAINING_NOW) is None
    assert service.current_phase(TRAINING_NOW) == PHASE_IDLE
    assert store.get_period_state(CB_PERIOD) is not None  # 記録は残る


def test_stop_when_not_running_returns_none(store):
    assert make_service(store).stop(TRAINING_NOW) is None


def test_offset_mode_needs_no_start(store):
    service = make_service(store, mode=MODE_OFFSET)
    assert service.current_phase(TRAINING_NOW) == PHASE_TRAINING
    assert service.current_period(TRAINING_NOW).cb_period == CB_PERIOD


def test_override_switches_to_manual_mode(store):
    service = make_service(store)
    period = service.override("2026-07-21", "2026-07-24", "2026-07-28")

    assert service.config.schedule.mode == MODE_MANUAL
    assert period.training_start.day == 21
    assert period.battle_start.day == 24
    assert period.battle_end.day == 28
    assert store.get_period_state(CB_PERIOD) is not None


def test_override_rejects_unparseable_dates(store):
    with pytest.raises(ValueError):
        make_service(store).override(None, "not-a-date", "2026-07-28")


# ---- 通知フラグ ----


def test_claim_notice_is_one_shot(store):
    service = make_service(store)
    service.start(TRAINING_NOW)

    assert service.claim_notice(CB_PERIOD, "training") is True
    assert service.claim_notice(CB_PERIOD, "training") is False
    assert service.claim_notice(CB_PERIOD, "battle") is True  # 種別ごとに独立


# ---- /start 催促（11-1 決定） ----


def test_reminder_is_due_once_when_start_forgotten(store, monkeypatch):
    freeze_now(monkeypatch, TRAINING_NOW)
    service = make_service(store)

    first = service.pending_reminder(TRAINING_NOW)
    assert first is not None
    assert first.cb_period == CB_PERIOD
    assert service.pending_reminder(TRAINING_NOW) is None  # 2回目は出ない


def test_no_reminder_before_the_offset_training_start(store, monkeypatch):
    early = datetime(2026, 7, 20, 3, 0, tzinfo=UTC)  # offset のトレモ開始は 7/23
    freeze_now(monkeypatch, early)
    assert make_service(store).pending_reminder(early) is None


def test_no_reminder_after_start(store, monkeypatch):
    freeze_now(monkeypatch, TRAINING_NOW)
    service = make_service(store)
    service.start(TRAINING_NOW)
    assert service.pending_reminder(TRAINING_NOW) is None


def test_no_reminder_when_disabled_or_not_trigger_mode(store, monkeypatch):
    freeze_now(monkeypatch, TRAINING_NOW)
    disabled = make_service(store, remind_if_not_started=False)
    assert disabled.pending_reminder(TRAINING_NOW) is None

    offset_mode = make_service(store, mode=MODE_OFFSET)
    assert offset_mode.pending_reminder(TRAINING_NOW) is None


# ---- 期間キーの探索 ----


@pytest.mark.parametrize(
    ("local_now", "expected"),
    [
        (datetime(2026, 7, 24), ["2026-07", "2026-06"]),
        (datetime(2026, 1, 3), ["2026-01", "2025-12"]),  # 年をまたぐ
    ],
)
def test_candidate_period_keys(local_now, expected):
    assert candidate_period_keys(local_now) == expected


def test_period_started_late_is_found_after_the_month_rolls_over(store):
    """月末開始の期間が翌月に食い込んでも見失わないこと。"""
    started = datetime(2026, 12, 29, 3, 0, tzinfo=UTC)
    service = make_service(store)
    service.start(started)

    next_month = datetime(2027, 1, 1, 3, 0, tzinfo=UTC)
    assert service.trigger_started_at(next_month) == started
