"""metadata.py のテスト。トレモ判定はタイトル/説明文のキーワードのみを根拠にする。"""

import pytest

from priconne_cb_collector.domain.classify.metadata import extract_metadata


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
    assert extract_metadata(text).damage == expected


@pytest.mark.parametrize(
    ("text", "full_auto", "manual"),
    [
        ("フルオート編成", True, None),
        ("フルオ", True, None),
        ("full auto", True, None),
        ("fullauto", True, None),
        ("手動編成", None, True),
        ("マニュアル操作", None, True),
        ("通常編成", None, None),
    ],
)
def test_full_auto_and_manual(text, full_auto, manual):
    result = extract_metadata(text)
    assert result.is_full_auto is full_auto
    assert result.is_manual is manual


@pytest.mark.parametrize(
    ("text", "is_training"),
    [
        ("トレーニングモードで検証", True),
        ("トレモ 検証", True),
        ("練習モードにて", True),
        ("検証動画", True),
        ("ワイバーン 通常凸", False),
        ("", False),
    ],
)
def test_training_footage_is_keyword_only(text, is_training):
    assert extract_metadata(text).is_training_footage is is_training


def test_extraction_failure_does_not_raise():
    """抽出失敗は None にとどめ、判定全体を落とさない（docs/spec/06 §4）。"""
    result = extract_metadata("")
    assert result.damage is None
    assert result.is_full_auto is None
    assert result.is_manual is None
    assert result.is_training_footage is False
