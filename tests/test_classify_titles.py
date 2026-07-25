"""実際の動画タイトルを模した表形式テスト（docs/spec/10 §3: 30件以上必須）。

各行: (タイトル, 説明文, 期待ボス indices, 期待 match_source, 期待 battle_type)
published_in_period=True / enable_ex_notation=True で分類する。
"""
import pytest

from classify import classify_video
from conftest import SAMPLE_BOSSES

CASES = [
    # --- ボス名・エイリアス一致 ---
    ("【プリコネR】7月クラバト ワイバーン 通常凸 2150万", "", [1], "boss_name", "normal"),
    ("【プリコネ】デミカリ 35秒持ち越し 1200万ダメージ", "", [2], "boss_name", "carryover"),
    ("雷電 フルオート編成【クラバト5段階目】", "", [3], "boss_name", "unknown"),
    ("スピホン 初手フルタイム 90秒 手動", "", [4], "boss_name", "normal"),
    ("オルレ 持越45秒 2段階目", "", [5], "boss_name", "carryover"),
    ("【プリコネR】クラバト 4ボス スピリットホーン 5段階目 通常", "", [4], "boss_name", "normal"),
    ("wyvern 1段階目 フルオート", "", [1], "boss_name", "unknown"),
    ("ＷＹＶＥＲＮ討伐！通常編成", "", [1], "boss_name", "normal"),  # 全角→半角正規化
    ("Wyvern Full Auto 2000万", "", [1], "boss_name", "unknown"),  # 大文字→小文字
    ("タイトルに無し", "説明文にワイバーンの編成解説あり", [1], "boss_name", "unknown"),  # 説明文も見る
    ("【プリコネR】第2ボス デミカリド 3段階目", "", [2], "boss_name", "unknown"),
    ("ライデン(雷電) 90秒フル", "", [3], "boss_name", "normal"),
    ("オルレオン 繰り越し20秒", "", [5], "boss_name", "carryover"),
    ("デミカリド戦 素凸編成【クラバト】", "", [2], "boss_name", "normal"),
    ("スピリットホーン もちこし 60秒から", "", [4], "boss_name", "carryover"),
    # --- 複数ヒット・まとめ動画 ---
    ("ワイバーン&デミカリド比較 通常", "", [1, 2], "boss_name", "normal"),
    ("【クラバト】ワイバーン/ライデン/オルレオン 全編成まとめ", "", [1, 3, 5], "boss_name", "unknown"),
    # --- EX表記（ボス名なし + プリコネ文脈語 + 期間内） ---
    ("【プリコネ】クラバト ex2 検証 トレモ", "", [2], "ex_notation", "unknown"),
    ("【プリコネR】4ボス 通常 フルオート", "クラバト編成", [4], "ex_notation", "normal"),
    ("プリコネ クラバト EX 1 攻略", "", [1], "ex_notation", "unknown"),
    ("【プリコネ】EX-3 持ち越し編成", "", [3], "ex_notation", "carryover"),
    ("クラバト ボス5 20秒スタート", "", [5], "ex_notation", "carryover"),
    ("プリコネ 第3ボス フルオート編成", "", [3], "ex_notation", "unknown"),
    ("【プリコネ】④ 3段階目 通常凸", "", [4], "ex_notation", "normal"),  # 丸数字
    ("priconne clan battle ex5 guide", "", [5], "ex_notation", "unknown"),
    # --- EX表記が適用されないケース ---
    ("EX-3 攻略動画", "", [], None, "unknown"),  # プリコネ文脈語なし
    ("4ボスの倒し方", "", [], None, "unknown"),  # 文脈語なし
    ("モンスト ex1 周回", "", [], None, "unknown"),  # 他ゲーム・文脈語なし
    # --- ボス名と EX表記の衝突 → ボス名優先 ---
    ("【プリコネ】ワイバーン ex2 説明欄参照", "", [1], "boss_name", "unknown"),
    # --- ボス判定不能 ---
    ("【プリコネ】ガチャ200連", "", [], None, "unknown"),
    ("クランバトルおつかれ雑談", "", [], None, "unknown"),
    # --- 通常/持ち越しの表記ゆれ ---
    ("ワイバン 持越し30秒 4段階", "", [1], "boss_name", "carryover"),
    ("デミカリ 繰越 15秒", "", [2], "boss_name", "carryover"),
    ("ライデン 初凸 1.5億", "", [3], "boss_name", "normal"),
    ("スピホン 1凸目 フルオート", "", [4], "boss_name", "normal"),
    ("オルレオン 持ち込み編成紹介", "", [5], "boss_name", "unknown"),  # 「持ち」単体は誤爆させない
    ("ワイバーン フルオ編成", "", [1], "boss_name", "unknown"),  # フルオ≠フルタイム
]


@pytest.mark.parametrize(
    ("title", "description", "indices", "source", "battle_type"),
    CASES,
    ids=[c[0][:30] for c in CASES],
)
def test_title_table(title, description, indices, source, battle_type):
    result = classify_video(
        title,
        description,
        SAMPLE_BOSSES,
        enable_ex_notation=True,
        published_in_period=True,
    )
    assert result.boss.indices == indices
    assert result.boss.match_source == source
    assert result.battle_type == battle_type


def test_case_count_meets_spec_minimum():
    assert len(CASES) >= 30
