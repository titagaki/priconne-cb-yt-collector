"""config.py の読み込み・バリデーションのテスト。"""

import logging

import pytest

from priconne_cb_collector.adapters.config_file import ConfigError, load_bosses, load_config

VALID_BOSSES = """\
month: "2026-07"
bosses:
  - index: 1
    name: "ワイバーン"
    aliases: ["ワイバーン", "ワイバン"]
  - index: 2
    name: "デミカリド"
  - index: 3
    name: "ライデン"
  - index: 4
    name: "スピリットホーン"
  - index: 5
    name: "オルレオン"
"""


def write(tmp_path, text):
    p = tmp_path / "bosses.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_valid_bosses(tmp_path):
    cfg = load_bosses(write(tmp_path, VALID_BOSSES))
    assert cfg.month == "2026-07"
    assert [b.index for b in cfg.bosses] == [1, 2, 3, 4, 5]
    assert cfg.by_index(1).aliases == ("ワイバーン", "ワイバン")
    # aliases 省略時は name のみ
    assert cfg.by_index(2).aliases == ("デミカリド",)


def test_bosses_must_be_exactly_five(tmp_path):
    text = VALID_BOSSES.rsplit("  - index: 5", 1)[0]  # 5体目を削る
    with pytest.raises(ConfigError, match="exactly 5"):
        load_bosses(write(tmp_path, text))


def test_duplicate_index_fails(tmp_path):
    text = VALID_BOSSES.replace("index: 2", "index: 1", 1)
    with pytest.raises(ConfigError, match="duplicate"):
        load_bosses(write(tmp_path, text))


def test_index_out_of_range_fails(tmp_path):
    text = VALID_BOSSES.replace("index: 5", "index: 6", 1)
    with pytest.raises(ConfigError, match="index must be 1-5"):
        load_bosses(write(tmp_path, text))


def test_invalid_month_fails(tmp_path):
    text = VALID_BOSSES.replace('month: "2026-07"', 'month: "July 2026"')
    with pytest.raises(ConfigError, match="month"):
        load_bosses(write(tmp_path, text))


def test_short_alias_warns_but_loads(tmp_path, caplog):
    text = VALID_BOSSES.replace('["ワイバーン", "ワイバン"]', '["ワイバーン", "ワイ"]')
    with caplog.at_level(logging.WARNING):
        cfg = load_bosses(write(tmp_path, text))
    assert cfg.by_index(1).aliases == ("ワイバーン", "ワイ")
    assert any("short alias" in r.message for r in caplog.records)


def test_missing_file_fails(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_bosses(tmp_path / "nope.yaml")


def test_load_repo_config():
    """リポジトリ同梱の config.yaml が読めて、既定が 11-1 の決定どおりであること。"""
    cfg = load_config("config/config.yaml")
    assert cfg.schedule.mode == "trigger"
    assert cfg.schedule.remind_if_not_started is True
    assert cfg.classify.enable_ex_notation is True
    assert cfg.discord.layout == "per_boss_thread"
    assert cfg.youtube.quota_limit_per_day == 9000
    assert "ガチャ" in cfg.youtube.exclude.title_ng_words


def test_invalid_mode_fails(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("schedule:\n  mode: sometimes\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="schedule.mode"):
        load_config(p)
