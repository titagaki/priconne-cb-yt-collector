"""battle_type.py のテスト（docs/spec/10 §3 の必須ケース）。"""
import pytest

from classify.battle_type import (
    BATTLE_CARRYOVER,
    BATTLE_NORMAL,
    BATTLE_UNKNOWN,
    classify_battle_type,
)

# (入力, 期待 battle_type, 期待 carryover_sec)
CASES = [
    # --- 持ち越し表記のゆれ ---
    ("持ち越し編成", BATTLE_CARRYOVER, None),
    ("持越し編成", BATTLE_CARRYOVER, None),
    ("持越", BATTLE_CARRYOVER, None),
    ("もちこし", BATTLE_CARRYOVER, None),
    ("繰り越し", BATTLE_CARRYOVER, None),
    ("繰越", BATTLE_CARRYOVER, None),
    # --- 秒数の抽出 ---
    ("35秒持ち越し", BATTLE_CARRYOVER, 35),
    ("持ち越し35秒", BATTLE_CARRYOVER, 35),
    ("持越20秒", BATTLE_CARRYOVER, 20),
    ("45秒から", BATTLE_CARRYOVER, 45),
    ("60秒スタート", BATTLE_CARRYOVER, 60),
    ("30秒start", BATTLE_CARRYOVER, 30),
    ("９０秒持ち越し", BATTLE_CARRYOVER, 90),  # 全角数字
    ("1秒持ち越し", BATTLE_CARRYOVER, 1),  # 下限
    # --- 範囲外の秒数は捨てるが、持ち越し自体は成立させる ---
    ("99秒持ち越し", BATTLE_CARRYOVER, None),
    ("0秒持ち越し", BATTLE_CARRYOVER, None),
    # --- 通常 ---
    ("通常編成", BATTLE_NORMAL, None),
    ("通常凸", BATTLE_NORMAL, None),
    ("通常", BATTLE_NORMAL, None),
    ("初手", BATTLE_NORMAL, None),
    ("初凸", BATTLE_NORMAL, None),
    ("素凸", BATTLE_NORMAL, None),
    ("1凸目", BATTLE_NORMAL, None),
    ("フルタイム", BATTLE_NORMAL, None),
    ("90秒", BATTLE_NORMAL, None),
    ("フル", BATTLE_NORMAL, None),
    # --- フル と フルオート の切り分け ---
    ("フルオート", BATTLE_UNKNOWN, None),
    ("フルオ", BATTLE_UNKNOWN, None),
    ("full auto", BATTLE_UNKNOWN, None),
    ("フルオート編成 90秒", BATTLE_NORMAL, None),  # 90秒 側で normal
    # --- 「持ち」単体を誤爆させない ---
    ("持ち込み編成", BATTLE_UNKNOWN, None),
    ("気持ちよく討伐", BATTLE_UNKNOWN, None),
    ("手持ちキャラ紹介", BATTLE_UNKNOWN, None),
    # --- 両方ヒット時は持ち越しを優先 ---
    ("持ち越し35秒（通常時より火力低め）", BATTLE_CARRYOVER, 35),
    ("通常編成と持ち越し編成の比較", BATTLE_CARRYOVER, None),
    # --- 判定不能 ---
    ("ワイバーン討伐", BATTLE_UNKNOWN, None),
    ("", BATTLE_UNKNOWN, None),
]


@pytest.mark.parametrize(
    ("text", "expected_type", "expected_sec"), CASES, ids=[c[0][:24] or "empty" for c in CASES]
)
def test_battle_type_table(text, expected_type, expected_sec):
    result = classify_battle_type(text)
    assert result.battle_type == expected_type
    assert result.carryover_sec == expected_sec


def test_matched_string_is_recorded_for_tuning():
    """判定チューニングのため、マッチ文字列の記録は必須（docs/spec/10 §2）。"""
    assert classify_battle_type("35秒持ち越し").matched_string is not None
    assert classify_battle_type("通常凸").matched_string is not None
    assert classify_battle_type("ワイバーン").matched_string is None
