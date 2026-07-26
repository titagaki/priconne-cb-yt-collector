"""収集パイプラインの結合テスト（検索 → 補完 → 判定 → DB 保存）。

search.list / videos.list はダミークライアントで差し替える。
Discord へは投稿せず、DB の status だけを検証する。
"""

from datetime import UTC, datetime, timedelta

import pytest

from priconne_cb_collector.adapters.youtube_api import QuotaExceededError, YouTubeClient
from priconne_cb_collector.domain.models import VideoMeta
from priconne_cb_collector.domain.settings import (
    ON_UNKNOWN_SKIP,
    AppConfig,
    ClassifyConfig,
    ExcludeConfig,
    YoutubeConfig,
)
from priconne_cb_collector.services.collection import (
    REASON_BOSS_UNKNOWN,
    REASON_LIVE,
    REASON_NG_WORD,
    REASON_TOO_LONG,
    REASON_TOO_SHORT,
    Collector,
)
from tests.support import bosses_config, july_period

PERIOD = july_period()
NOW = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)  # 収集期間中

# bosses_config() のボス名を OR で連結したもの
EXPECTED_QUERY = "ワイバーン OR デミカリド OR ライデン OR スピリットホーン OR オルレオン"


def found(vid, title, published=None):
    """search.list が返す1件分。description / 尺は videos.list で補完される。"""
    return VideoMeta(
        video_id=vid,
        title=title,
        channel_id="UC_test",
        published_at=published or datetime(2026, 7, 24, 2, 0, tzinfo=UTC),
        channel_title="テストチャンネル",
    )


class FakeYouTube(YouTubeClient):
    """videos.list / search.list を差し替えたクライアント。"""

    def __init__(self, details=None, search_results=None, raise_quota=False, raise_error=False):
        self.details = details or {}
        self.search_results = search_results or []
        self.raise_quota = raise_quota
        self.raise_error = raise_error
        self.search_calls = []

    async def enrich_videos(self, video_ids):
        if self.raise_quota:
            raise QuotaExceededError("quotaExceeded")
        return {vid: self.details[vid] for vid in video_ids if vid in self.details}, 1

    async def search_videos(self, query, published_after, max_results=50):
        self.search_calls.append(query)
        if self.raise_quota:
            raise QuotaExceededError("quotaExceeded")
        if self.raise_error:
            raise RuntimeError("boom")
        return list(self.search_results), 100


def detail(duration="PT5M30S", description="", live=None, views="1000"):
    item = {
        "snippet": {"description": description, "channelTitle": "テストチャンネル"},
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": views},
    }
    if live is not None:
        item["liveStreamingDetails"] = live
        item["snippet"]["liveBroadcastContent"] = "live"
    return item


def make_config(exclude=None, quota_limit_per_day=9000, classify=None):
    return AppConfig(
        youtube=YoutubeConfig(
            quota_limit_per_day=quota_limit_per_day,
            # config.yaml と同じ既定値
            exclude=exclude or ExcludeConfig(title_ng_words=("ガチャ", "雑談", "実況プレイ")),
        ),
        classify=classify or ClassifyConfig(),
    )


def make_collector(store, youtube, config=None):
    return Collector(config or make_config(), bosses_config(), store, youtube)


async def run_collect(store, videos, details=None, config=None):
    youtube = FakeYouTube(details=details or {}, search_results=videos)
    return await make_collector(store, youtube, config).collect(PERIOD, now=NOW)


# ---- 検索クエリ ----


def test_search_query_joins_every_boss_with_or(store):
    """1クエリ100ユニット固定なので、5ボスを1回にまとめる（docs/spec/05 §1）。"""
    assert make_collector(store, FakeYouTube()).search_query() == EXPECTED_QUERY


@pytest.mark.asyncio
async def test_one_round_issues_exactly_one_search(store):
    youtube = FakeYouTube()
    await make_collector(store, youtube).collect(PERIOD, now=NOW)

    assert youtube.search_calls == [EXPECTED_QUERY]


# ---- 取得 → 保存 ----


@pytest.mark.asyncio
async def test_search_to_db_happy_path(store):
    videos = [found("vid_a", "【プリコネ】ワイバーン 通常凸 2150万")]
    result = await run_collect(store, videos, {"vid_a": detail()})

    assert result.fetched == 1
    assert result.new == 1
    assert result.pending == 1
    row = store.get_video("vid_a")
    assert row["status"] == "pending"
    assert row["boss_index"] == 1
    assert row["battle_type"] == "normal"
    assert row["damage"] == 2150
    assert row["duration_sec"] == 330
    assert row["cb_period"] == "2026-07"


@pytest.mark.asyncio
async def test_description_is_used_for_classification(store):
    """videos.list で補完された説明文が判定に使われること。"""
    videos = [found("vid_b", "今日の攻略動画")]
    details = {"vid_b": detail(description="デミカリド 35秒持ち越しの編成です")}
    await run_collect(store, videos, details)

    row = store.get_video("vid_b")
    assert row["boss_index"] == 2
    assert row["battle_type"] == "carryover"
    assert row["carryover_sec"] == 35
    assert row["status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("title", "detail_kwargs", "reason"),
    [
        ("ワイバーン 通常凸", {"duration": "PT30S"}, REASON_TOO_SHORT),
        ("ワイバーン 通常凸", {"duration": "PT2H"}, REASON_TOO_LONG),
        (
            "ワイバーン 通常凸",
            {"live": {"scheduledStartTime": "2026-07-25T00:00:00Z"}},
            REASON_LIVE,
        ),
        ("ワイバーン ガチャ100連", {}, REASON_NG_WORD),
    ],
)
async def test_excluded_videos_are_saved_but_not_postable(store, title, detail_kwargs, reason):
    """除外対象も保存はする（docs/spec/06 §5）。"""
    result = await run_collect(store, [found("vid_x", title)], {"vid_x": detail(**detail_kwargs)})

    assert result.filtered == 1
    assert result.pending == 0
    row = store.get_video("vid_x")
    assert row["status"] == "filtered"
    assert row["filter_reason"] == reason


@pytest.mark.asyncio
async def test_unclassified_video_is_posted_by_default(store):
    """取りこぼすくらいなら関係ない動画が混ざってよい（docs/spec/01 §2）。"""
    result = await run_collect(store, [found("vid_u", "今月の編成まとめ")], {"vid_u": detail()})

    row = store.get_video("vid_u")
    assert row["boss_index"] is None
    assert row["status"] == "pending"  # 親チャンネルへ投稿される
    assert result.pending == 1
    assert result.filtered == 0


@pytest.mark.asyncio
async def test_unclassified_video_is_filtered_when_skip_is_configured(store):
    config = make_config(classify=ClassifyConfig(on_boss_unknown=ON_UNKNOWN_SKIP))
    result = await run_collect(
        store, [found("vid_u", "今月の編成まとめ")], {"vid_u": detail()}, config=config
    )

    row = store.get_video("vid_u")
    assert row["status"] == "filtered"
    assert row["filter_reason"] == REASON_BOSS_UNKNOWN
    assert result.pending == 0


@pytest.mark.asyncio
async def test_finished_archive_is_not_treated_as_live(store):
    details = {
        "vid_arc": {
            "snippet": {"description": "", "liveBroadcastContent": "none"},
            "contentDetails": {"duration": "PT20M"},
            "statistics": {"viewCount": "50"},
            "liveStreamingDetails": {"actualEndTime": "2026-07-24T01:00:00Z"},
        }
    }
    await run_collect(store, [found("vid_arc", "ワイバーン 通常凸")], details)
    assert store.get_video("vid_arc")["status"] == "pending"


@pytest.mark.asyncio
async def test_already_known_videos_are_skipped(store):
    videos = [found("vid_a", "ワイバーン 通常凸")]
    first = await run_collect(store, videos, {"vid_a": detail()})
    second = await run_collect(store, videos, {"vid_a": detail()})

    assert first.new == 1
    assert second.fetched == 1
    assert second.new == 0
    assert second.pending == 0


@pytest.mark.asyncio
async def test_one_bad_video_does_not_abort_the_run(store, monkeypatch):
    """1件の判定失敗でジョブ全体を落とさない（docs/spec/10 §1）。"""
    from priconne_cb_collector.services import collection as collector_module

    real_classify = collector_module.classify_video

    def flaky(title, *args, **kwargs):
        if "壊れた" in title:
            raise ValueError("boom")
        return real_classify(title, *args, **kwargs)

    monkeypatch.setattr(collector_module, "classify_video", flaky)

    videos = [found("vid_ok", "ワイバーン 通常凸"), found("vid_bad", "壊れたデータ ライデン")]
    result = await run_collect(store, videos, {"vid_ok": detail(), "vid_bad": detail()})

    assert result.errors == 1
    assert result.pending == 1
    assert store.get_video("vid_ok")["status"] == "pending"
    assert store.get_video("vid_bad")["status"] == "error"


@pytest.mark.asyncio
async def test_search_failure_does_not_raise(store):
    """検索が落ちてもジョブは落とさない。次の巡回で拾い直す。"""
    collector = make_collector(store, FakeYouTube(raise_error=True))
    result = await collector.collect(PERIOD, now=NOW)

    assert result.fetched == 0
    assert result.errors == 0
    assert result.search_skipped is False  # クォータ由来のスキップではない


# ---- クォータ管理 ----


@pytest.mark.asyncio
async def test_one_round_costs_one_search(store):
    """5ボスを1クエリにまとめたので 1巡 = 100 ユニット。"""
    youtube = FakeYouTube()
    result = await make_collector(store, youtube).collect(PERIOD, now=NOW)

    assert len(youtube.search_calls) == 1
    assert result.quota_used == 100
    assert store.quota_used(NOW) == 100


@pytest.mark.asyncio
async def test_search_skipped_when_quota_would_be_exceeded(store):
    store.add_quota(8950, NOW)  # 上限 9000 に対し 100 消費すると超える
    youtube = FakeYouTube()
    result = await make_collector(store, youtube).collect(PERIOD, now=NOW)

    assert youtube.search_calls == []
    assert result.search_skipped is True
    assert store.quota_used(NOW) == 8950


@pytest.mark.asyncio
async def test_quota_exceeded_blocks_further_searches_today(store):
    """quotaExceeded はリトライせず、その日の検索を止める（docs/spec/05 §4）。"""
    youtube = FakeYouTube(raise_quota=True)
    result = await make_collector(store, youtube).collect(PERIOD, now=NOW)

    assert result.search_skipped is True
    assert result.fetched == 0
    assert store.quota_used(NOW) >= 9000  # その日の検索は以後スキップされる


@pytest.mark.asyncio
async def test_ex_notation_requires_publication_within_period(store):
    """期間前に投稿された EX表記動画は今月のボスに割り当てない（docs/spec/06 §2.2）。"""
    old = PERIOD.start - timedelta(days=40)
    videos = [found("vid_old", "【プリコネ】クラバト 4ボス 通常凸", published=old)]
    result = await run_collect(store, videos, {"vid_old": detail()})

    row = store.get_video("vid_old")
    assert row["boss_index"] is None  # 「4ボス」を今月の4ボスに割り当てない
    assert row["match_source"] is None
    # ボス不明でも既定では投稿する（docs/spec/01 §2）
    assert row["status"] == "pending"
    assert result.pending == 1


# ---- クォータのログ（roadmap 監査 B） ----


async def test_daily_quota_total_is_logged_at_info(store, caplog):
    """日次の消費合計を INFO で残す（docs/spec/10 §2）。"""
    import logging

    store.add_quota(1200, NOW)  # その日すでに消費済みの分
    with caplog.at_level(logging.INFO, logger="priconne_cb_collector.services.collection"):
        await make_collector(store, FakeYouTube()).collect(PERIOD, now=NOW)

    summaries = [r.message for r in caplog.records if "quota daily total" in r.message]
    assert len(summaries) == 1
    assert "used=1300" in summaries[0]  # 1200 + 検索 100
    assert "limit=9000" in summaries[0]
    assert "date=2026-07-24" in summaries[0]  # JST の日付
