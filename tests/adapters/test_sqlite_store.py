"""sqlite_store.py のテスト（docs/spec/10 §3 の必須ケース）。"""

from datetime import UTC, datetime, timedelta

from priconne_cb_collector.adapters.sqlite_store import STATUS_POSTED
from priconne_cb_collector.domain.models import BossMatch, Classification, VideoMeta
from priconne_cb_collector.domain.schedule import JST
from tests.support import july_period


def make_video(video_id="abc123", **kwargs):
    defaults = dict(
        video_id=video_id,
        title="【プリコネ】ワイバーン 通常凸",
        channel_id="UC_test",
        channel_title="テストチャンネル",
        published_at=datetime(2026, 7, 24, 3, 0, tzinfo=UTC),
        description="説明文",
        duration_sec=300,
    )
    defaults.update(kwargs)
    return VideoMeta(**defaults)


def make_classification(indices=(1,), battle_type="normal"):
    return Classification(
        boss=BossMatch(indices=list(indices), match_source="boss_name"),
        battle_type=battle_type,
    )


def add(store, video, classification=None, **kwargs):
    return store.add_video(
        video,
        classification or make_classification(),
        cb_period=kwargs.pop("cb_period", "2026-07"),
        **kwargs,
    )


# ---- 重複 INSERT ----


def test_insert_then_duplicate_is_ignored(store):
    assert add(store, make_video()) is True
    assert add(store, make_video()) is False
    assert store.get_video("abc123")["title"] == "【プリコネ】ワイバーン 通常凸"


def test_duplicate_insert_does_not_reset_posted_status(store):
    """再収集で status が posted から pending に戻ってはいけない。"""
    add(store, make_video())
    store.mark_posted("abc123", 999888777)

    add(store, make_video(title="別タイトルで再収集"))

    row = store.get_video("abc123")
    assert row["status"] == STATUS_POSTED
    assert row["discord_msg_id"] == "999888777"
    assert row["title"] == "【プリコネ】ワイバーン 通常凸"


def test_known_video_ids_filters_candidates(store):
    add(store, make_video("aaa"))
    add(store, make_video("bbb"))
    assert store.known_video_ids(["aaa", "ccc"]) == {"aaa"}
    assert store.known_video_ids([]) == set()


def test_classification_fields_round_trip(store):
    classification = Classification(
        boss=BossMatch(indices=[3], match_source="boss_name"),
        battle_type="carryover",
        carryover_sec=35,
        damage=2150,
    )
    add(store, make_video(), classification)
    row = store.get_video("abc123")
    assert row["boss_index"] == 3
    assert row["match_source"] == "boss_name"
    assert row["carryover_sec"] == 35
    assert row["damage"] == 2150


def test_multiple_boss_hits_are_stored_as_undecided(store):
    """複数ヒットは判定不能。経路も残さない（docs/spec/06 §2.1、07 §1）。"""
    classification = Classification(boss=BossMatch(indices=[1, 3], match_source="boss_name"))
    add(store, make_video(), classification)
    row = store.get_video("abc123")
    assert row["boss_index"] is None
    assert row["match_source"] is None


def test_status_transitions(store):
    add(store, make_video("v1"))
    add(store, make_video("v2"))
    add(store, make_video("v3"))
    assert len(store.pending_videos("2026-07")) == 3

    store.mark_posted("v1", 1)
    store.mark_filtered("v2", "too_short")
    store.mark_error("v3", "classify failed")

    assert len(store.pending_videos("2026-07")) == 0
    assert store.get_video("v2")["filter_reason"] == "too_short"
    assert store.get_video("v3")["status"] == "error"


# ---- 開始 / 終了 通知フラグ ----


def test_notification_flag_prevents_duplicate_announcements(store):
    store.ensure_period(july_period())
    assert store.mark_notified("2026-07", "start") is True
    assert store.mark_notified("2026-07", "start") is False  # 再起動しても再投稿しない
    assert store.is_notified("2026-07", "start") is True
    # 他の種別は独立
    assert store.is_notified("2026-07", "end") is False
    assert store.mark_notified("2026-07", "end") is True


def test_notice_flags_are_independent(store):
    store.ensure_period(july_period())
    assert store.mark_notified("2026-07", "end") is True
    assert store.mark_notified("2026-07", "end") is False
    assert store.is_notified("2026-07", "start") is False


def test_ensure_period_is_idempotent(store):
    store.ensure_period(july_period())
    store.mark_notified("2026-07", "start")
    store.ensure_period(july_period())  # 再起動時の再呼び出しでフラグが消えないこと
    assert store.is_notified("2026-07", "start") is True


def test_open_and_close_period(store):
    p = july_period()
    assert store.open_period_start("2026-07") is None
    store.open_period(p)
    assert store.open_period_start("2026-07") == p.start
    store.close_period("2026-07")
    assert store.open_period_start("2026-07") is None


def test_reopening_clears_the_notice_flags(store):
    """/start し直したら開始通知をもう一度出す（再起動時は出さない）。"""
    p = july_period()
    store.open_period(p)
    store.mark_notified("2026-07", "start")
    store.mark_notified("2026-07", "end")

    store.close_period("2026-07")
    store.open_period(p)

    assert store.is_notified("2026-07", "start") is False
    assert store.is_notified("2026-07", "end") is False


def test_boss_threads_round_trip(store):
    store.ensure_period(july_period())
    assert store.load_boss_threads("2026-07") == {}
    store.save_boss_threads("2026-07", {1: 111, 2: 222})
    assert store.load_boss_threads("2026-07") == {1: 111, 2: 222}


# ---- クォータ ----


def test_quota_accumulates_per_jst_day(store):
    now = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)  # JST 12:00
    assert store.quota_used(now) == 0
    assert store.add_quota(100, now) == 100
    assert store.add_quota(1, now) == 101

    # JST の日付が変われば別カウント（UTC 15:00 = 翌日 00:00 JST）
    next_day = datetime(2026, 7, 24, 15, 0, tzinfo=UTC)
    assert store.quota_used(next_day) == 0


def test_quota_boundary_is_jst_midnight_not_utc(store):
    before = datetime(2026, 7, 24, 14, 59, 59, tzinfo=UTC)  # JST 23:59:59
    after = datetime(2026, 7, 24, 15, 0, 0, tzinfo=UTC)  # JST 翌日 00:00
    store.add_quota(500, before)
    assert store.quota_used(before) == 500
    assert store.quota_used(after) == 0


# ---- 日次投稿上限のカウント ----


def test_count_posted_today_per_boss(store):
    now = datetime(2026, 7, 26, 6, 0, tzinfo=UTC)  # JST 15:00
    for i in range(3):
        add(store, make_video(f"boss1_{i}"), make_classification((1,)))
        store.mark_posted(f"boss1_{i}", i, now)
    add(store, make_video("boss2_0"), make_classification((2,)))
    store.mark_posted("boss2_0", 99, now)
    add(store, make_video("boss1_pending"), make_classification((1,)))  # 未投稿は数えない

    assert store.count_posted_today(1, now) == 3
    assert store.count_posted_today(2, now) == 1
    assert store.count_posted_today(3, now) == 0


def test_count_posted_today_resets_next_jst_day(store):
    now = datetime(2026, 7, 26, 6, 0, tzinfo=UTC)
    add(store, make_video("v1"))
    store.mark_posted("v1", 1, now)
    assert store.count_posted_today(1, now) == 1
    tomorrow = now + timedelta(days=1)
    assert store.count_posted_today(1, tomorrow) == 0


# ---- 集計 ----


def test_count_by_boss(store):
    add(store, make_video("a"), make_classification((1,)))
    add(store, make_video("b"), make_classification((1,)))
    add(store, make_video("c"), make_classification((2,)))
    add(store, make_video("d"), Classification(boss=BossMatch()))  # 判定不能
    counts = store.count_by_boss("2026-07")
    assert counts[1] == 2
    assert counts[2] == 1
    assert counts[None] == 1


def test_pending_videos_scoped_to_period(store):
    add(store, make_video("jul"), cb_period="2026-07")
    add(store, make_video("aug"), cb_period="2026-08")
    assert [r["video_id"] for r in store.pending_videos("2026-07")] == ["jul"]


def test_recent_videos_filtered_by_boss(store):
    add(store, make_video("a"), make_classification((1,)))
    add(store, make_video("b"), make_classification((2,)))
    assert len(store.recent_videos("2026-07")) == 2
    assert [r["video_id"] for r in store.recent_videos("2026-07", boss_index=2)] == ["b"]


def test_datetimes_stored_as_utc(store):
    """JST で渡しても DB には UTC で入る（docs/spec/07）。"""
    published_jst = datetime(2026, 7, 24, 12, 0, tzinfo=JST)
    add(store, make_video(published_at=published_jst))
    assert store.get_video("abc123")["published_at"].startswith("2026-07-24T03:00:00+00:00")
