"""Optional metadata extraction (docs/spec/06 §4). All fields may be None."""
from __future__ import annotations

import re
from dataclasses import dataclass

from classify.normalize import normalize

_PHASE = re.compile(r"([1-5])\s?段階|段階\s?([1-5])")
# 億 optionally followed by a 万 remainder ("2億3000万"), else 万 alone.
_DAMAGE_OKU = re.compile(r"(\d+(?:\.\d+)?)\s?億\s?(?:(\d+)\s?万)?")
_DAMAGE_MAN = re.compile(r"(\d+(?:\.\d+)?)\s?万")
_FULL_AUTO = re.compile(r"フルオート|full\s?auto|フルオ")
_MANUAL = re.compile(r"手動|マニュアル")
_TRAINING = re.compile(r"トレーニングモード|トレモ|練習モード|検証")

EVIDENCE_KEYWORD = "keyword"
EVIDENCE_PHASE_ONLY = "phase_only"


@dataclass(frozen=True)
class MetadataResult:
    boss_phase: int | None = None
    damage: int | None = None  # in units of 万
    is_full_auto: bool | None = None
    is_manual: bool | None = None
    is_training_footage: bool = False
    training_evidence: str | None = None


def extract_metadata(raw_text: str, *, discovered_phase: str | None = None) -> MetadataResult:
    """discovered_phase: bot phase at collection time ("training" | "battle")."""
    norm = normalize(raw_text)
    # commas inside numbers ("2,150万") would break the damage patterns
    norm_numeric = re.sub(r"(?<=\d),(?=\d)", "", norm)

    phase_match = _PHASE.search(norm)
    boss_phase = None
    if phase_match:
        boss_phase = int(phase_match.group(1) or phase_match.group(2))

    damage = _extract_damage(norm_numeric)

    keyword_hit = bool(_TRAINING.search(norm))
    if keyword_hit:
        evidence = EVIDENCE_KEYWORD
    elif discovered_phase == "training":
        evidence = EVIDENCE_PHASE_ONLY
    else:
        evidence = None

    return MetadataResult(
        boss_phase=boss_phase,
        damage=damage,
        is_full_auto=True if _FULL_AUTO.search(norm) else None,
        is_manual=True if _MANUAL.search(norm) else None,
        is_training_footage=evidence is not None,
        training_evidence=evidence,
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
