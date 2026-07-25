"""Normal vs carryover decision (docs/spec/06 §3). Pure functions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from priconne_cb_collector.domain.classify.normalize import normalize
from priconne_cb_collector.domain.models import (
    BATTLE_CARRYOVER,
    BATTLE_NORMAL,
    BATTLE_UNKNOWN,
)

# Carryover patterns. "持ち" alone is deliberately excluded (持ち込み/気持ち).
_CARRYOVER_WORD = re.compile(r"持ち越し|持越し|持越|もちこし")
# Seconds are written far more often as "24s" than "24秒" in real titles
# (docs/game/video-conventions.md), so both units are accepted.
_SEC = r"(?:秒|s)"
_CARRYOVER_SEC_BEFORE = re.compile(
    rf"(\d{{1,2}})\s?{_SEC}\s?(?:持ち越し|持越し|持越|から|スタート|start)"
)
_CARRYOVER_SEC_AFTER = re.compile(rf"(?:持ち越し|持越し|持越)\s?(\d{{1,2}})\s?{_SEC}")
# A bare "34s" with no carryover word still means carryover: a full-time run is
# 90 seconds, so any shorter figure is time inherited from the previous 凸.
# 90 is excluded because bare "90s" reads as full time, not a max carryover.
_CARRYOVER_SEC_BARE = re.compile(r"(?<![a-z0-9])([1-8]?[0-9])\s?s(?![a-z0-9])")

# Normal patterns. フル needs a lookahead so フルオート/フルオ (full-auto,
# a separate attribute) is not mistaken for "full time".
_NORMAL = re.compile(r"通常編成|通常凸|通常|初手|初凸|素凸|1凸目|フルタイム|90秒|90s|フル(?!オ)")

_MIN_CARRYOVER_SEC = 1
_MAX_CARRYOVER_SEC = 90


@dataclass(frozen=True)
class BattleTypeResult:
    battle_type: str
    carryover_sec: int | None = None
    matched_string: str | None = None


def classify_battle_type(raw_text: str) -> BattleTypeResult:
    """Carryover wins over normal when both patterns hit (spec §3.3)."""
    norm = normalize(raw_text)

    carryover_match = _CARRYOVER_WORD.search(norm)
    sec: int | None = None
    sec_match = (
        _CARRYOVER_SEC_AFTER.search(norm)
        or _CARRYOVER_SEC_BEFORE.search(norm)
        or _CARRYOVER_SEC_BARE.search(norm)
    )
    if sec_match:
        value = int(sec_match.group(1))
        if _MIN_CARRYOVER_SEC <= value <= _MAX_CARRYOVER_SEC:
            sec = value

    if carryover_match or sec_match:
        matched = (carryover_match or sec_match).group(0)
        return BattleTypeResult(BATTLE_CARRYOVER, carryover_sec=sec, matched_string=matched)

    normal_match = _NORMAL.search(norm)
    if normal_match:
        return BattleTypeResult(BATTLE_NORMAL, matched_string=normal_match.group(0))

    return BattleTypeResult(BATTLE_UNKNOWN)
