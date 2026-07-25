"""Normal vs carryover decision (docs/spec/06 §3). Pure functions."""
from __future__ import annotations

import re
from dataclasses import dataclass

from classify.normalize import normalize

BATTLE_NORMAL = "normal"
BATTLE_CARRYOVER = "carryover"
BATTLE_UNKNOWN = "unknown"

# Carryover patterns. "持ち" alone is deliberately excluded (持ち込み/気持ち).
_CARRYOVER_WORD = re.compile(r"持ち越し|持越し|持越|もちこし|繰り越し|繰越")
_CARRYOVER_SEC_BEFORE = re.compile(r"(\d{1,2})\s?秒\s?(?:持ち越し|持越し|持越|から|スタート|start)")
_CARRYOVER_SEC_AFTER = re.compile(r"(?:持ち越し|持越し|持越)\s?(\d{1,2})\s?秒")

# Normal patterns. フル needs a lookahead so フルオート/フルオ (full-auto,
# a separate attribute) is not mistaken for "full time".
_NORMAL = re.compile(
    r"通常編成|通常凸|通常|初手|初凸|素凸|1凸目|フルタイム|90秒|フル(?!オ)"
)

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
    sec_match = _CARRYOVER_SEC_AFTER.search(norm) or _CARRYOVER_SEC_BEFORE.search(norm)
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
