"""store.py のテスト（docs/spec/02 §3）。"""

from datetime import UTC, datetime

from priconne_cb_collector.store import period_key
from tests.support import CB_PERIOD, STARTED


def test_only_posted_videos_are_recorded(store):
    """投稿に成功したものだけ記録する。失敗分は次の巡回で再試行される。"""
    assert store.known_video_ids(["v1"]) == set()

    store.mark_posted("v1", "ワイバーン 通常凸", 1, CB_PERIOD, STARTED)

    assert store.known_video_ids(["v1", "v2"]) == {"v1"}
    assert store.known_video_ids([]) == set()


def test_reposting_the_same_video_is_ignored(store):
    store.mark_posted("v1", "元のタイトル", 1, CB_PERIOD, STARTED)
    store.mark_posted("v1", "別タイトルで再収集", 2, CB_PERIOD, STARTED)

    assert store.count_by_boss(CB_PERIOD) == {1: 1}


def test_count_by_boss_includes_undecided(store):
    store.mark_posted("v1", "ワイバーン", 1, CB_PERIOD, STARTED)
    store.mark_posted("v2", "ワイバーン", 1, CB_PERIOD, STARTED)
    store.mark_posted("v3", "ライデン", 3, CB_PERIOD, STARTED)
    store.mark_posted("v4", "まとめ", None, CB_PERIOD, STARTED)

    assert store.count_by_boss(CB_PERIOD) == {1: 2, 3: 1, None: 1}
    assert store.count_by_boss("2026-08") == {}


# ---- 収集期間 ----


def test_open_and_close_period(store):
    assert store.current_period() is None

    period = store.open_period(STARTED)
    assert period.cb_period == CB_PERIOD
    assert store.current_period() == period

    store.close_period(CB_PERIOD)
    assert store.current_period() is None


def test_period_survives_a_restart(store):
    """再起動時は is_open だけを見て再開する（docs/spec/03）。"""
    store.open_period(STARTED)

    reopened = store.current_period()
    assert reopened is not None
    assert reopened.start == STARTED


def test_starting_again_overwrites_the_start_time(store):
    store.open_period(STARTED)
    store.close_period(CB_PERIOD)

    later = datetime(2026, 7, 25, 3, 0, tzinfo=UTC)
    store.open_period(later)

    assert store.current_period().start == later


def test_period_key_is_the_jst_month_of_the_start():
    """月をまたいでもキーは開始月のまま（docs/spec/03）。"""
    assert period_key(STARTED) == "2026-07"
    # UTC 7/31 16:00 は JST では 8/1
    assert period_key(datetime(2026, 7, 31, 16, 0, tzinfo=UTC)) == "2026-08"


def test_an_open_period_keeps_its_key_into_the_next_month(store):
    store.open_period(STARTED)
    # 8月に入っても、開いているのは7月のキーのまま
    assert store.current_period().cb_period == "2026-07"
