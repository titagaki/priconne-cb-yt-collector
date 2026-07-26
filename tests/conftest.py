"""共通フィクスチャ。定数とテストダブルは tests/support.py にある。"""

import pytest

from priconne_cb_collector.store import Store
from tests.support import SAMPLE_BOSSES, bosses_config


@pytest.fixture
def bosses():
    return SAMPLE_BOSSES


@pytest.fixture
def bosses_cfg():
    return bosses_config()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()
