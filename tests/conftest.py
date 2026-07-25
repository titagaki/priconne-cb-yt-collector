import pytest

from models import Boss

# docs/spec/03 のサンプル構成と同じ（テスト専用。bosses.yaml の正は運用者が管理）
SAMPLE_BOSSES = (
    Boss(1, "ワイバーン", ("ワイバーン", "ワイバン", "wyvern")),
    Boss(2, "デミカリド", ("デミカリド", "デミカリ")),
    Boss(3, "ライデン", ("ライデン", "雷電")),
    Boss(4, "スピリットホーン", ("スピリットホーン", "スピホン")),
    Boss(5, "オルレオン", ("オルレオン", "オルレ")),
)


@pytest.fixture
def bosses():
    return SAMPLE_BOSSES
