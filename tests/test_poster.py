"""poster.py のテスト。Discord へは繋がず、送信先をダミーに差し替える。"""
from datetime import datetime, timezone

import discord
import pytest

from discord_bot.poster import REASON_DAILY_LIMIT, Poster, build_embed
from models import AppConfig, BossesConfig, BossMatch, Classification, DiscordConfig, VideoMeta
from schedule import JST
from store import Store

from conftest import SAMPLE_BOSSES

BOSSES = BossesConfig(month="2026-07", bosses=SAMPLE_BOSSES)
NOW = datetime(2026, 7, 26, 6, 0, tzinfo=timezone.utc)  # JST 15:00


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "poster.db")
    yield s
    s.close()


def add_video(store, video_id="vid1", title="【プリコネ】ワイバーン 通常凸", **fields):
    classification = Classification(
        boss=BossMatch(
            indices=fields.pop("indices", [1]),
            match_source=fields.pop("match_source", "boss_name"),
            is_summary=fields.pop("is_summary", False),
        ),
        battle_type=fields.pop("battle_type", "normal"),
        carryover_sec=fields.pop("carryover_sec", None),
        boss_phase=fields.pop("boss_phase", None),
        damage=fields.pop("damage", None),
        is_full_auto=fields.pop("is_full_auto", None),
        is_manual=fields.pop("is_manual", None),
        is_training_footage=fields.pop("is_training_footage", False),
        training_evidence=fields.pop("training_evidence", None),
    )
    video = VideoMeta(
        video_id=video_id,
        title=title,
        channel_id=fields.pop("channel_id", "UC_test"),
        channel_title="テストチャンネル",
        published_at=datetime(2026, 7, 26, 5, 0, tzinfo=timezone.utc),
        discovered_via="rss",
        description="この説明文は Embed に転載してはいけない",
    )
    store.add_video(
        video,
        classification,
        discovered_phase=fields.pop("discovered_phase", "battle"),
        cb_period="2026-07",
    )
    return store.get_video(video_id)


# ---- Embed ----

def test_embed_never_reproduces_the_description(store):
    """説明文を Embed に転載しない（docs/spec/08 §2）。"""
    row = add_video(store)
    embed = build_embed(row, BOSSES)

    assert embed.description in (None, "")
    rendered = str(embed.to_dict())
    assert "転載してはいけない" not in rendered
    assert embed.url == "https://www.youtube.com/watch?v=vid1"
    assert embed.title == "【プリコネ】ワイバーン 通常凸"


def test_embed_fields_for_carryover(store):
    row = add_video(
        store, battle_type="carryover", carryover_sec=35, boss_phase=4, damage=2150
    )
    embed = build_embed(row, BOSSES)
    fields = {f.name: f.value for f in embed.fields}

    assert fields["ボス"] == "1ボス ワイバーン"
    assert fields["種別"] == "持ち越し (35秒)"
    assert fields["段階"] == "4段階"
    assert fields["ダメージ"] == "2,150万"


def test_embed_omits_optional_fields_when_absent(store):
    row = add_video(store)
    fields = {f.name for f in build_embed(row, BOSSES).fields}
    assert fields == {"ボス", "種別"}


@pytest.mark.parametrize(
    ("battle_type", "expected"),
    [("normal", "通常"), ("carryover", "持ち越し"), ("unknown", "不明")],
)
def test_battle_type_labels(store, battle_type, expected):
    row = add_video(store, battle_type=battle_type)
    fields = {f.name: f.value for f in build_embed(row, BOSSES).fields}
    assert fields["種別"] == expected


@pytest.mark.parametrize(
    ("evidence", "badge"),
    [("keyword", "🏋️ トレモ"), ("phase_only", "🏋️ トレモ期間")],
)
def test_training_badges_distinguish_evidence(store, evidence, badge):
    """推定（phase_only）と確証（keyword）を表示上区別する（docs/spec/08 §2）。"""
    row = add_video(store, is_training_footage=True, training_evidence=evidence)
    assert badge in build_embed(row, BOSSES).footer.text


def test_ex_notation_badge(store):
    row = add_video(store, match_source="ex_notation")
    assert "※EX表記から推定" in build_embed(row, BOSSES).footer.text


def test_footer_has_channel_and_jst_time(store):
    row = add_video(store, is_full_auto=True)
    footer = build_embed(row, BOSSES).footer.text
    assert "テストチャンネル" in footer
    assert "07/26 14:00" in footer  # UTC 05:00 → JST 14:00
    assert "フルオート" in footer


def test_summary_video_lists_every_boss(store):
    row = add_video(store, indices=[1, 3, 5], is_summary=True)
    fields = {f.name: f.value for f in build_embed(row, BOSSES).fields}
    assert fields["ボス"].startswith("まとめ:")
    assert "3ボス ライデン" in fields["ボス"]


def test_boss_colors_are_distinct_per_index(store):
    colors = set()
    for index in range(1, 6):
        row = add_video(store, video_id=f"v{index}", indices=[index])
        colors.add(build_embed(row, BOSSES).color.value)
    assert len(colors) == 5


# ---- 投稿制御 ----

class FakeMessage:
    def __init__(self, message_id):
        self.id = message_id


class FakeChannel:
    def __init__(self, channel_id=100, fail_with=None):
        self.id = channel_id
        self.sent = []
        self.fail_with = fail_with
        self._next_id = 1000

    async def send(self, content=None, embed=None):
        if self.fail_with is not None:
            raise self.fail_with
        self._next_id += 1
        self.sent.append((content, embed))
        return FakeMessage(self._next_id)


class FakeBot:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel

    async def fetch_channel(self, channel_id):
        return self.channel


def make_poster(store, channel, **discord_overrides):
    config = AppConfig(
        discord=DiscordConfig(
            layout=discord_overrides.pop("layout", "single"),
            channel_id=100,
            max_posts_per_boss_per_day=discord_overrides.pop("max_posts_per_boss_per_day", 15),
            post_interval_seconds=0,
        )
    )
    return Poster(FakeBot(channel), config, BOSSES, store)


async def test_pending_videos_are_posted_and_marked(store):
    channel = FakeChannel()
    poster = make_poster(store, channel)
    add_video(store, "vid1")
    add_video(store, "vid2")

    posted = await poster.post_pending("2026-07", NOW)

    assert posted == 2
    assert len(channel.sent) == 2
    assert store.get_video("vid1")["status"] == "posted"
    assert store.get_video("vid1")["discord_msg_id"] is not None
    assert store.pending_videos("2026-07") == []


async def test_status_stays_pending_when_discord_fails(store):
    """投稿成功時のみ posted にする（docs/spec/08 §3）。"""
    channel = FakeChannel(fail_with=discord.HTTPException(_FakeResponse(500), "boom"))
    poster = make_poster(store, channel)
    add_video(store, "vid1")

    posted = await poster.post_pending("2026-07", NOW)

    assert posted == 0
    assert store.get_video("vid1")["status"] == "pending"  # 次回リトライされる


async def test_daily_limit_filters_the_excess(store):
    channel = FakeChannel()
    poster = make_poster(store, channel, max_posts_per_boss_per_day=2)
    for i in range(4):
        add_video(store, f"vid{i}")

    posted = await poster.post_pending("2026-07", NOW)

    assert posted == 2
    assert store.get_video("vid2")["status"] == "filtered"
    assert store.get_video("vid2")["filter_reason"] == REASON_DAILY_LIMIT
    # 上限到達の通知は1回だけ
    notices = [c for c, _ in channel.sent if c]
    assert len(notices) == 1
    assert "上限" in notices[0]


async def test_daily_limit_is_per_boss(store):
    channel = FakeChannel()
    poster = make_poster(store, channel, max_posts_per_boss_per_day=1)
    add_video(store, "boss1_a", indices=[1])
    add_video(store, "boss1_b", indices=[1])
    add_video(store, "boss2_a", indices=[2])

    await poster.post_pending("2026-07", NOW)

    assert store.get_video("boss1_a")["status"] == "posted"
    assert store.get_video("boss1_b")["status"] == "filtered"
    assert store.get_video("boss2_a")["status"] == "posted"


async def test_unlimited_when_cap_is_zero(store):
    channel = FakeChannel()
    poster = make_poster(store, channel, max_posts_per_boss_per_day=0)
    for i in range(5):
        add_video(store, f"vid{i}")

    assert await poster.post_pending("2026-07", NOW) == 5


async def test_boss_threads_are_reused_across_restarts(store):
    class ThreadChannel(FakeChannel):
        def __init__(self):
            super().__init__()
            self.created = []

        async def create_thread(self, name, type=None):
            self._next_id += 1
            self.created.append(name)
            return FakeMessage(self._next_id)

    channel = ThreadChannel()
    poster = make_poster(store, channel, layout="per_boss_thread")
    store.ensure_period(_period())

    first = await poster.ensure_boss_threads("2026-07")
    assert len(first) == 5
    assert channel.created[0] == "1ボス: ワイバーン"

    channel.created.clear()
    second = await poster.ensure_boss_threads("2026-07")
    assert second == first
    assert channel.created == []  # 既存スレッドを作り直さない


def _period():
    from models import Period

    return Period(
        training_start=datetime(2026, 7, 23, tzinfo=JST),
        battle_start=datetime(2026, 7, 26, tzinfo=JST),
        battle_end=datetime(2026, 7, 30, 23, 59, 59, tzinfo=JST),
        cb_period="2026-07",
    )


class _FakeResponse:
    """discord.HTTPException requires an object with a status attribute."""

    def __init__(self, status):
        self.status = status
        self.reason = "fake"
