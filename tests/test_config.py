"""config.py のテスト。壊れた設定は起動時に落とす（docs/spec/05）。"""

import pytest

from priconne_cb_collector.config import ConfigError, load_bosses, load_config
from tests.support import FALLBACK_CHANNEL, make_config

VALID_BOSSES = """
month: "2026-07"
bosses:
  - {index: 1, name: ワイバーン, aliases: [ワイバーン, ワイバン]}
  - {index: 2, name: デミカリド}
  - {index: 3, name: ライデン, aliases: [ライデン, 雷電]}
  - {index: 4, name: スピリットホーン}
  - {index: 5, name: オルレオン}
"""

VALID_CONFIG = """
polling:
  search_interval_minutes: 15
youtube:
  search_lookback_days: 2
  title_ng_words: ["ガチャ"]
discord:
  boss_channels: {1: 101, 2: 102, 3: 103, 4: 104, 5: 105}
  fallback_channel_id: 900
  post_interval_seconds: 3
"""


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_a_valid_bosses_file(tmp_path):
    cfg = load_bosses(write(tmp_path, "bosses.yaml", VALID_BOSSES))

    assert cfg.month == "2026-07"
    assert [b.index for b in cfg.bosses] == [1, 2, 3, 4, 5]
    assert cfg.by_index(3).aliases == ("ライデン", "雷電")
    # aliases 省略時は name 自身が候補になる
    assert cfg.by_index(2).aliases == ("デミカリド",)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("month: 2026-7\nbosses: []", "月の形式"),
        ('month: "2026-07"\nbosses: []', "5体ちょうどでない"),
        ('month: "2026-07"\nbosses: [{index: 9, name: X}]', "index が範囲外"),
    ],
)
def test_invalid_bosses_file_raises(tmp_path, text, reason):
    with pytest.raises(ConfigError):
        load_bosses(write(tmp_path, "bosses.yaml", text))


def test_loads_a_valid_config(tmp_path):
    cfg = load_config(write(tmp_path, "config.yaml", VALID_CONFIG))

    assert cfg.search_interval_minutes == 15
    assert cfg.search_lookback_days == 2
    assert cfg.title_ng_words == ("ガチャ",)
    assert cfg.post_interval_seconds == 3
    assert cfg.boss_channels == {1: 101, 2: 102, 3: 103, 4: 104, 5: 105}
    assert cfg.fallback_channel_id == 900


def test_missing_fallback_channel_is_fatal(tmp_path):
    """投稿先が1つも無いと動画を捨てることになるので起動させない。"""
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, "config.yaml", "discord: {boss_channels: {1: 101}}"))


def test_missing_boss_channels_fall_back_instead_of_failing(tmp_path):
    """一部のボスだけ未設定なら、その分は fallback へ流す（起動は止めない）。"""
    text = "discord:\n  boss_channels: {1: 101}\n  fallback_channel_id: 900\n"
    cfg = load_config(write(tmp_path, "config.yaml", text))

    assert cfg.channel_for(1) == 101
    assert cfg.channel_for(4) == 900


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does-not-exist.yaml")


def test_channel_for_routes_undecided_videos_to_the_fallback():
    cfg = make_config()
    assert cfg.channel_for(2) == 102
    assert cfg.channel_for(None) == FALLBACK_CHANNEL
