"""ボス名マッチと NG ワードのテスト（docs/spec/04）。

各行: (タイトル, 期待する boss_index)。None は「1体に特定できず」。
"""

import pytest

from priconne_cb_collector.classify import is_ng, match_boss, normalize
from priconne_cb_collector.config import Boss
from tests.support import SAMPLE_BOSSES

CASES = [
    # --- ボス名・エイリアス一致 ---
    ("【プリコネR】7月クラバト ワイバーン 通常凸 2150万", 1),
    ("【プリコネ】デミカリ 35秒持ち越し 1200万ダメージ", 2),
    ("雷電 フルオート編成【クラバト5段階目】", 3),
    ("スピホン 初手フルタイム 90秒 手動", 4),
    ("オルレ 持越45秒 2段階目", 5),
    ("【プリコネR】クラバト 4ボス スピリットホーン 5段階目 通常", 4),
    ("デミカリド戦 素凸編成【クラバト】", 2),
    ("スピリットホーン もちこし 60秒から", 4),
    ("ライデン(雷電) 90秒フル", 3),
    # --- 正規化 ---
    ("wyvern 1段階目 フルオート", 1),  # 小文字エイリアス
    ("ＷＹＶＥＲＮ討伐！通常編成", 1),  # 全角 → 半角
    ("Wyvern Full Auto 2000万", 1),  # 大文字 → 小文字
    # --- 複数ヒットは特定できず ---
    ("ワイバーン&デミカリド比較 通常", None),
    ("【クラバト】ワイバーン/ライデン/オルレオン 全編成まとめ", None),
    # --- ヒットなし ---
    ("【プリコネ】ガチャ200連", None),
    ("クランバトルおつかれ雑談", None),
    ("EX-3 攻略動画", None),  # 番号表記は判定に使わない
    ("4ボスの倒し方", None),
]


@pytest.mark.parametrize(("title", "expected"), CASES, ids=[c[0][:30] for c in CASES])
def test_boss_match_table(title, expected):
    assert match_boss(title, SAMPLE_BOSSES) is expected


def test_case_count_meets_spec_minimum():
    assert len(CASES) >= 15


def test_name_is_matched_even_when_aliases_omit_it():
    """aliases は name を置き換えるのではなく補う（docs/spec/04）。

    bosses.yaml で name="デミ・カリド" / aliases=["デミカリド"] のように
    name そのものを aliases に書かない運用があり、実データではこの形で
    ボス名が一切ヒットしなくなっていた。
    """
    bosses = (Boss(2, "デミ・カリド", ("デミカリド",)),)
    assert match_boss("【プリコネR】4段階目 デミ・カリド 14071万 38s持ち越し編成", bosses) == 2


def test_normalize_keeps_katakana():
    assert "ワイバーン" in normalize("【ワイバーン】")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("【プリコネ】ガチャ200連", True),
        ("クラバト後の雑談配信", True),
        ("ワイバーン 通常凸", False),
        ("", False),
    ],
)
def test_ng_words(title, expected):
    assert is_ng(title, ("ガチャ", "雑談")) is expected
