"""schedule.py のテスト（docs/spec/10 の必須ケース）。"""

from datetime import UTC, datetime, timedelta

import pytest

from priconne_cb_collector.domain.schedule import (
    JST,
    candidate_period_keys,
    is_collecting,
    make_period,
    period_key,
)


def jst(*args):
    return datetime(*args, tzinfo=JST)


# ---- 期間の生成: 開始は /start の時刻そのもの ----


def test_period_starts_at_the_moment_it_was_opened():
    started = jst(2026, 7, 23, 14, 30, 0)
    p = make_period(started)
    assert p.start == started
    assert p.cb_period == "2026-07"


def test_period_has_no_end():
    """終了日は存在しない。/stop されるまで収集し続ける。"""
    assert not hasattr(make_period(jst(2026, 7, 23)), "end")


# ---- 収集する / しないの境界（前後1秒） ----


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (jst(2026, 7, 23, 14, 29, 59), False),  # 開始 1秒前
        (jst(2026, 7, 23, 14, 30, 0), True),  # 開始ちょうど
        (jst(2026, 7, 23, 14, 30, 1), True),  # 開始 1秒後
        (jst(2026, 7, 26, 12, 0, 0), True),  # 途中
        (jst(2026, 8, 30, 12, 0, 0), True),  # 月をまたいでも終わらない
    ],
)
def test_collection_boundaries(now, expected):
    p = make_period(jst(2026, 7, 23, 14, 30, 0))
    assert is_collecting(now, p) is expected


def test_no_period_never_collects():
    """/stop 後は期間そのものが無くなるので収集しない。"""
    assert is_collecting(jst(2026, 7, 26), None) is False


# ---- 期間キー: 開始した JST の月 ----


@pytest.mark.parametrize(
    ("started", "expected"),
    [
        (jst(2026, 7, 23, 14, 30), "2026-07"),
        (jst(2026, 7, 31, 23, 59), "2026-07"),
        (datetime(2026, 7, 31, 16, 0, tzinfo=UTC), "2026-08"),  # JST では 8/1 01:00
    ],
)
def test_period_key(started, expected):
    assert period_key(started) == expected


def test_key_does_not_change_when_the_month_rolls_over():
    """月末に開始した収集は、翌月に食い込んでも開始月のキーのまま。"""
    p = make_period(jst(2026, 7, 29, 21, 0))
    assert p.cb_period == "2026-07"


@pytest.mark.parametrize(
    ("local_now", "expected"),
    [
        (datetime(2026, 7, 24), ["2026-07", "2026-06"]),
        (datetime(2026, 1, 3), ["2026-01", "2025-12"]),  # 年をまたぐ
    ],
)
def test_candidate_period_keys(local_now, expected):
    assert candidate_period_keys(local_now) == expected


# ---- タイムゾーン: UTC で渡しても JST 基準で判定される ----


def test_collecting_with_utc_input():
    # 2026-07-23 00:00 JST == 2026-07-22 15:00 UTC
    p = make_period(jst(2026, 7, 23, 0, 0, 0))
    utc_now = datetime(2026, 7, 22, 15, 0, 0, tzinfo=UTC)
    assert is_collecting(utc_now, p) is True
    assert is_collecting(utc_now - timedelta(seconds=1), p) is False
