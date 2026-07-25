"""Optional metadata extraction (docs/spec/06 §4). All fields may be None."""

from __future__ import annotations

import re
from dataclasses import dataclass

from priconne_cb_collector.domain.classify.normalize import normalize

# 億 optionally followed by a 万 remainder ("2億3000万"), else 万 alone.
_DAMAGE_OKU = re.compile(r"(\d+(?:\.\d+)?)\s?億\s?(?:(\d+)\s?万)?")
_DAMAGE_MAN = re.compile(r"(\d+(?:\.\d+)?)\s?万")
_FULL_AUTO = re.compile(r"フルオート|full\s?auto|フルオ")
_MANUAL = re.compile(r"手動|マニュアル")
_TRAINING = re.compile(r"トレーニングモード|トレモ|練習モード|検証")


@dataclass(frozen=True)
class MetadataResult:
    damage: int | None = None  # in units of 万
    is_full_auto: bool | None = None
    is_manual: bool | None = None
    is_training_footage: bool = False


def extract_metadata(raw_text: str) -> MetadataResult:
    norm = normalize(raw_text)
    # commas inside numbers ("2,150万") would break the damage patterns
    norm_numeric = re.sub(r"(?<=\d),(?=\d)", "", norm)

    return MetadataResult(
        damage=_extract_damage(norm_numeric),
        is_full_auto=True if _FULL_AUTO.search(norm) else None,
        is_manual=True if _MANUAL.search(norm) else None,
        is_training_footage=bool(_TRAINING.search(norm)),
    )


def _extract_damage(norm_numeric: str) -> int | None:
    oku = _DAMAGE_OKU.search(norm_numeric)
    if oku:
        total = float(oku.group(1)) * 10000
        if oku.group(2):
            total += int(oku.group(2))
        return int(round(total))
    man = _DAMAGE_MAN.search(norm_numeric)
    if man:
        return int(round(float(man.group(1))))
    return None
