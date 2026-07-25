"""収集パイプラインの結合テスト（取得 → 判定 → DB 保存）。

RSS は httpx.MockTransport、videos.list はダミークライアントで差し替える。
Discord へは投稿せず、DB の status だけを検証する。
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from conftest import SAMPLE_BOSSES
from priconne_cb_collector.adapters.sqlite_store import Store
from priconne_cb_collector.adapters.youtube_api import QuotaExceededError, YouTubeClient
from priconne_cb_collector.domain.models import BossesConfig, Period
from priconne_cb_collector.domain.schedule import JST
from priconne_cb_collector.domain.settings import (
    AppConfig,
    ChannelRef,
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

PERIOD = Period(
    training_start=datetime(2026, 7, 23, tzinfo=JST),
    battle_start=datetime(2026, 7, 26, tzinfo=JST),
    battle_end=datetime(2026, 7, 30, 23, 59, 59, tzinfo=JST),
    cb_period="2026-07",
)
NOW = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)  # training 期間中

FEED_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
  <title>テストチャンネル</title>
  {entries}
</feed>
"""
ENTRY_TEMPLATE = """
  <entry>
    <id>yt:video:{vid}</id>
    <yt:videoId>{vid}</yt:videoId>
    <yt:channelId>UC_test</yt:channelId>
    <title>{title}</title>
    <author><name>テストチャンネル</name></author>
    <published>{published}</published>
  </entry>
"""


def make_feed(entries):
    body = "".join(
        ENTRY_TEMPLATE.format(
            vid=vid, title=title, published=published or "2026-07-24T02:00:00+00:00"
        )
        for vid, title, published in entries
    )
    return FEED_TEMPLATE.format(entries=body)


class FakeYouTube(YouTubeClient):
    """videos.list / search.list を差し替えたクライアント。"""

    def __init__(self, details=None, search_results=None, raise_quota=False):
        self.details = details or {}
        self.search_results = search_results or []
        self.raise_quota = raise_quota
        self.search_calls = []

    async def enrich_videos(self, video_ids):
        if self.raise_quota:
            raise QuotaExceededError("quotaExceeded")
        return {vid: self.details[vid] for vid in video_ids if vid in self.details}, 1

    async def search_videos(self, query, published_after, max_results=50):
        self.search_calls.append(query)
        if self.raise_quota:
            raise QuotaExceededError("quotaExceeded")
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


def make_config(exclude=None, quota_limit_per_day=9000):
    return AppConfig(
        youtube=YoutubeConfig(
            channels=(ChannelRef(id="UC_test", name="テスト"),),
            quota_limit_per_day=quota_limit_per_day,
            # config.yaml と同じ既定値
            exclude=exclude
            or ExcludeConfig(title_ng_words=("ガチャ", "雑談", "実況プレイ", "初心者")),
        )
    )


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "collector.db")
    yield s
    s.close()


def http_client(feed_body, status_code=200, headers=None):
    def handler(request):
        return httpx.Response(status_code, text=feed_body, headers=headers or {})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def run_collect(store, feed, details=None, config=None, **kwargs):
    async with http_client(feed) as client:
        collector = Collector(
            config or make_config(),
            BossesConfig(month="2026-07", bosses=SAMPLE_BOSSES),
            store,
            client,
            FakeYouTube(details=details or {}),
        )
        return await collector.collect(PERIOD, now=NOW, **kwargs)


@pytest.mark.asyncio
async def test_rss_to_db_happy_path(store):
    feed = make_feed([("vid_a", "【プリコネ】ワイバーン 通常凸 2150万", None)])
    result = await run_collect(store, feed, {"vid_a": detail()})

    assert result.fetched == 1
    assert result.new == 1
    assert result.pending == 1
    row = store.get_video("vid_a")
    assert row["status"] == "pending"
    assert row["boss_index"] == 1
    assert row["battle_type"] == "normal"
    assert row["damage"] == 2150
    assert row["duration_sec"] == 330
    assert row["discovered_phase"] == "training"
    assert row["cb_period"] == "2026-07"


@pytest.mark.asyncio
async def test_description_is_used_for_classification(store):
    """RSS にはない説明文が videos.list で補完され、判定に使われること。"""
    feed = make_feed([("vid_b", "今日の攻略動画", None)])
    details = {"vid_b": detail(description="デミカリド 35秒持ち越しの編成です")}
    await run_collect(store, feed, details)

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
        ("今月の編成まとめ", {}, REASON_BOSS_UNKNOWN),
    ],
)
async def test_excluded_videos_are_saved_but_not_postable(store, title, detail_kwargs, reason):
    """除外対象も保存はする（docs/spec/06 §5）。"""
    feed = make_feed([("vid_x", title, None)])
    result = await run_collect(store, feed, {"vid_x": detail(**detail_kwargs)})

    assert result.filtered == 1
    assert result.pending == 0
    row = store.get_video("vid_x")
    assert row["status"] == "filtered"
    assert row["filter_reason"] == reason


@pytest.mark.asyncio
async def test_finished_archive_is_not_treated_as_live(store):
    feed = make_feed([("vid_arc", "ワイバーン 通常凸", None)])
    details = {
        "vid_arc": {
            "snippet": {"description": "", "liveBroadcastContent": "none"},
            "contentDetails": {"duration": "PT20M"},
            "statistics": {"viewCount": "50"},
            "liveStreamingDetails": {"actualEndTime": "2026-07-24T01:00:00Z"},
        }
    }
    await run_collect(store, feed, details)
    assert store.get_video("vid_arc")["status"] == "pending"


@pytest.mark.asyncio
async def test_already_known_videos_are_skipped(store):
    feed = make_feed([("vid_a", "ワイバーン 通常凸", None)])
    first = await run_collect(store, feed, {"vid_a": detail()})
    second = await run_collect(store, feed, {"vid_a": detail()})

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

    feed = make_feed(
        [
            ("vid_ok", "ワイバーン 通常凸", None),
            ("vid_bad", "壊れたデータ ライデン", None),
        ]
    )
    result = await run_collect(store, feed, {"vid_ok": detail(), "vid_bad": detail()})

    assert result.errors == 1
    assert result.pending == 1
    assert store.get_video("vid_ok")["status"] == "pending"
    assert store.get_video("vid_bad")["status"] == "error"


@pytest.mark.asyncio
async def test_rss_304_yields_no_videos(store):
    store.save_etag("UC_test", 'W/"cached"', NOW)
    async with http_client("", status_code=304) as client:
        collector = Collector(
            make_config(),
            BossesConfig(month="2026-07", bosses=SAMPLE_BOSSES),
            store,
            client,
            FakeYouTube(),
        )
        result = await collector.collect(PERIOD, now=NOW)
    assert result.fetched == 0


@pytest.mark.asyncio
async def test_rss_failure_does_not_raise(store):
    async with http_client("", status_code=500) as client:
        collector = Collector(
            make_config(),
            BossesConfig(month="2026-07", bosses=SAMPLE_BOSSES),
            store,
            client,
            FakeYouTube(),
        )
        result = await collector.collect(PERIOD, now=NOW)
    assert result.fetched == 0
    assert result.errors == 0


# ---- クォータ管理 ----


@pytest.mark.asyncio
async def test_api_search_consumes_quota_per_boss(store):
    feed = make_feed([])
    async with http_client(feed) as client:
        youtube = FakeYouTube()
        collector = Collector(
            make_config(),
            BossesConfig(month="2026-07", bosses=SAMPLE_BOSSES),
            store,
            client,
            youtube,
        )
        result = await collector.collect(PERIOD, now=NOW, run_api_search=True)

    assert len(youtube.search_calls) == 5  # ボス5体で1巡
    assert result.quota_used == 500
    assert store.quota_used(NOW) == 500


@pytest.mark.asyncio
async def test_api_search_skipped_when_quota_would_be_exceeded(store):
    store.add_quota(8800, NOW)  # 上限 9000 に対し 500 消費すると超える
    feed = make_feed([])
    async with http_client(feed) as client:
        youtube = FakeYouTube()
        collector = Collector(
            make_config(),
            BossesConfig(month="2026-07", bosses=SAMPLE_BOSSES),
            store,
            client,
            youtube,
        )
        result = await collector.collect(PERIOD, now=NOW, run_api_search=True)

    assert youtube.search_calls == []
    assert result.api_search_skipped is True
    assert store.quota_used(NOW) == 8800


@pytest.mark.asyncio
async def test_quota_exceeded_degrades_to_rss_only(store):
    """quotaExceeded でも停止せず RSS の結果は処理される（docs/spec/05 §4）。"""
    feed = make_feed([("vid_a", "ワイバーン 通常凸", None)])
    async with http_client(feed) as client:
        youtube = FakeYouTube(raise_quota=True)
        collector = Collector(
            make_config(),
            BossesConfig(month="2026-07", bosses=SAMPLE_BOSSES),
            store,
            client,
            youtube,
        )
        result = await collector.collect(PERIOD, now=NOW, run_api_search=True)

    assert result.api_search_skipped is True
    assert result.new == 1
    # 補完なしでもタイトルだけで判定して保存される
    assert store.get_video("vid_a")["boss_index"] == 1
    assert store.quota_used(NOW) >= 9000  # その日の検索は以後スキップされる


@pytest.mark.asyncio
async def test_ex_notation_requires_publication_within_period(store):
    """期間前に投稿された EX表記動画は今月のボスに割り当てない（docs/spec/06 §2.2）。"""
    old = (PERIOD.training_start - timedelta(days=40)).astimezone(UTC).isoformat()
    feed = make_feed([("vid_old", "【プリコネ】クラバト 4ボス 通常凸", old)])
    result = await run_collect(store, feed, {"vid_old": detail()})

    row = store.get_video("vid_old")
    assert row["boss_index"] is None
    assert row["status"] == "filtered"
    assert row["filter_reason"] == REASON_BOSS_UNKNOWN
    assert result.pending == 0
