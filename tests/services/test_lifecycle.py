"""PeriodService のテスト（docs/spec/04）。Discord にも YouTube にも触れない。"""

from datetime import UTC, datetime

from priconne_cb_collector.services.lifecycle import PeriodService
from tests.support import CB_PERIOD

STARTED = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)  # JST 7/24 12:00
LATER = datetime(2026, 7, 27, 3, 0, tzinfo=UTC)
NEXT_MONTH = datetime(2026, 8, 3, 3, 0, tzinfo=UTC)


# ---- 期間の解決 ----


def test_idle_until_started(store):
    service = PeriodService(store)
    assert service.current_period(STARTED) is None
    assert service.is_collecting(STARTED) is False


def test_start_records_the_period_and_begins_collecting(store):
    service = PeriodService(store)
    period = service.start(STARTED)

    assert period.start == STARTED
    assert period.cb_period == CB_PERIOD
    assert service.is_collecting(STARTED) is True
    assert service.is_collecting(LATER) is True


def test_collection_does_not_end_on_its_own(store):
    """終了日が無いので、月をまたいでも /stop するまで収集中のまま。"""
    service = PeriodService(store)
    service.start(STARTED)
    assert service.is_collecting(NEXT_MONTH) is True
    assert service.current_period(NEXT_MONTH).cb_period == CB_PERIOD


def test_started_state_survives_a_new_service_instance(store):
    """再起動しても DB から収集中の状態を復元できること。"""
    PeriodService(store).start(STARTED)

    restarted = PeriodService(store)
    assert restarted.is_collecting(LATER) is True
    assert restarted.current_period(LATER).start == STARTED


def test_stop_returns_to_idle_without_deleting_data(store):
    service = PeriodService(store)
    service.start(STARTED)

    stopped = service.stop(STARTED)

    assert stopped.cb_period == CB_PERIOD
    assert service.current_period(STARTED) is None
    assert service.is_collecting(STARTED) is False
    assert store.get_period_state(CB_PERIOD) is not None  # 記録は残る


def test_stop_when_not_running_returns_none(store):
    assert PeriodService(store).stop(STARTED) is None


def test_restarting_the_same_month_uses_the_new_start_time(store):
    service = PeriodService(store)
    service.start(STARTED)
    service.stop(STARTED)

    service.start(LATER)
    assert service.current_period(LATER).start == LATER


# ---- 通知フラグ ----


def test_claim_notice_is_one_shot(store):
    service = PeriodService(store)
    service.start(STARTED)

    assert service.claim_notice(CB_PERIOD, "start") is True
    assert service.claim_notice(CB_PERIOD, "start") is False
    assert service.claim_notice(CB_PERIOD, "end") is True  # 種別ごとに独立


def test_starting_again_re_arms_the_notices(store):
    """再起動は黙るが、/start し直したら改めて開始通知を出す。"""
    service = PeriodService(store)
    service.start(STARTED)
    assert service.claim_notice(CB_PERIOD, "start") is True

    service.stop(STARTED)
    service.start(LATER)
    assert service.claim_notice(CB_PERIOD, "start") is True
