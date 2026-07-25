"""metadata.py のテスト。トレモ判定の根拠（keyword / phase_only）の区別が要点。"""
import pytest

from classify.metadata import EVIDENCE_KEYWORD, EVIDENCE_PHASE_ONLY, extract_metadata


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5段階目 ワイバーン", 5),
        ("段階3のボス", 3),
        ("1段階", 1),
        ("ワイバーン討伐", None),
        ("6段階目", None),  # 範囲外
    ],
)
def test_boss_phase(text, expected):
    assert extract_metadata(text).boss_phase == expected


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
    ("text", "discovered_phase", "is_training", "evidence"),
    [
        # キーワード由来（強い根拠）
        ("トレーニングモードで検証", "battle", True, EVIDENCE_KEYWORD),
        ("トレモ 5段階目", "battle", True, EVIDENCE_KEYWORD),
        ("練習モードにて", None, True, EVIDENCE_KEYWORD),
        ("検証動画", "training", True, EVIDENCE_KEYWORD),  # 期間中でもキーワードを優先
        # 期間由来のみ（弱い根拠）
        ("ワイバーン 通常凸", "training", True, EVIDENCE_PHASE_ONLY),
        # トレモではない
        ("ワイバーン 通常凸", "battle", False, None),
        ("ワイバーン 通常凸", None, False, None),
    ],
)
def test_training_footage_evidence(text, discovered_phase, is_training, evidence):
    result = extract_metadata(text, discovered_phase=discovered_phase)
    assert result.is_training_footage is is_training
    assert result.training_evidence == evidence


def test_extraction_failure_does_not_raise():
    """抽出失敗は None にとどめ、判定全体を落とさない（docs/spec/06 §4）。"""
    result = extract_metadata("")
    assert result.boss_phase is None
    assert result.damage is None
    assert result.is_full_auto is None
    assert result.training_evidence is None
