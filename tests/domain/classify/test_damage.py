"""damage.py のテスト。タイトル/説明文から抽出するのはダメージだけ（docs/spec/06 §4）。"""

import pytest

from priconne_cb_collector.domain.classify.damage import extract_damage


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2150万ダメージ", 2150),
        ("2,150万ダメージ", 2150),  # 桁区切りカンマ
        ("1.5億", 15000),
        ("2億3000万", 23000),
        ("１２００万", 1200),  # 全角
        ("編成紹介", None),
    ],
)
def test_damage_normalized_to_man(text, expected):
    assert extract_damage(text) == expected


def test_extraction_failure_does_not_raise():
    """抽出失敗は None にとどめ、判定全体を落とさない（docs/spec/06 §4）。"""
    assert extract_damage("") is None
