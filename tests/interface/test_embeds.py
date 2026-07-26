"""embeds.py のテスト（docs/spec/08 §2）。Discord へは接続しない。"""

import pytest

from priconne_cb_collector.interface.embeds import build_bosses_embed, build_video_embed
from tests.support import bosses_config, store_video

BOSSES = bosses_config()


def test_never_reproduces_the_description(store):
    """説明文を Embed に転載しない（docs/spec/08 §2）。"""
    embed = build_video_embed(store_video(store), BOSSES)

    assert embed.description in (None, "")
    assert "転載してはいけない" not in str(embed.to_dict())
    assert embed.url == "https://www.youtube.com/watch?v=vid1"
    assert embed.title == "【プリコネ】ワイバーン 通常凸"


def test_fields_for_carryover(store):
    row = store_video(store, battle_type="carryover", carryover_sec=35, damage=2150)
    fields = {f.name: f.value for f in build_video_embed(row, BOSSES).fields}

    assert fields["ボス"] == "1ボス ワイバーン"
    assert fields["種別"] == "持ち越し (35秒)"
    assert fields["ダメージ"] == "2,150万"


def test_optional_fields_are_omitted_when_absent(store):
    fields = {f.name for f in build_video_embed(store_video(store), BOSSES).fields}
    assert fields == {"ボス", "種別"}


@pytest.mark.parametrize(
    ("battle_type", "expected"),
    [("normal", "通常"), ("carryover", "持ち越し"), ("unknown", "不明")],
)
def test_battle_type_labels(store, battle_type, expected):
    row = store_video(store, battle_type=battle_type)
    fields = {f.name: f.value for f in build_video_embed(row, BOSSES).fields}
    assert fields["種別"] == expected


def test_ex_notation_badge(store):
    row = store_video(store, match_source="ex_notation")
    assert "※EX表記から推定" in build_video_embed(row, BOSSES).footer.text


def test_footer_has_channel_and_jst_time_only(store):
    """タイトルに書いてある内容はフッターに再掲しない（docs/spec/08 §2）。"""
    row = store_video(store, title="【プリコネ】ワイバーン フルオート トレモ検証")
    footer = build_video_embed(row, BOSSES).footer.text

    assert "テストチャンネル" in footer
    assert "07/26 14:00" in footer  # UTC 05:00 → JST 14:00
    assert "フルオート" not in footer
    assert "トレモ" not in footer


@pytest.mark.parametrize("indices", [[], [1, 3, 5]])
def test_undecided_video_says_so(store, indices):
    """ヒット0件も複数ヒットも同じ「判定できず」（docs/spec/06 §2.1）。"""
    row = store_video(store, indices=indices, match_source=None)
    fields = {f.name: f.value for f in build_video_embed(row, BOSSES).fields}
    assert fields["ボス"] == "判定できず"


def test_boss_colors_are_distinct_per_index(store):
    colors = {
        build_video_embed(store_video(store, f"v{i}", indices=[i]), BOSSES).color.value
        for i in range(1, 6)
    }
    assert len(colors) == 5


# ---- ボス一覧 Embed ----


def test_bosses_embed_lists_all_five():
    embed = build_bosses_embed(BOSSES, current_month="2026-07")
    names = [f.name for f in embed.fields]
    assert names == ["対象月", "1ボス", "2ボス", "3ボス", "4ボス", "5ボス"]
    assert embed.footer.text is None  # 月が一致していれば警告なし


def test_bosses_embed_warns_on_month_mismatch():
    """前月構成のまま運用していることを運用者が気付けるようにする。"""
    embed = build_bosses_embed(BOSSES, current_month="2026-08")
    assert "2026-07" in embed.footer.text
    assert "2026-08" in embed.footer.text
